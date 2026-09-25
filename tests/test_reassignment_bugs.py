"""Regression tests for bugs reported after manual testing of the
reassignment workflow:

1. `/api/v1/station-commander/dockets` (the list backing the detective
   dashboard's "Current Investigations" panel and the shared Active Cases /
   Evidence Vault pages) was gated to station_commander only, so every other
   operational role saw "Forbidden" in those content areas.
2. Reassigning a case to a new detective via the station commander's
   dashboard didn't transfer ownership of any already-open investigation, so
   the newly assigned detective was denied access to it.
3. A station commander could not assign a constable to a docket that hadn't
   been registered yet (AssignmentService required status == REGISTERED
   unconditionally), which is also why the target-officer dropdown was stuck
   on "Loading officers..." for unregistered dockets.
"""

import pytest

ROLE_TEST_IDS = {
    "citizen": "2200223333111",
    "constable": "2200223333114",
    "detective": "2200223333115",
    "station_commander": "2200223333116",
    "ipid": "2200223333117",
}


@pytest.fixture()
def app_client():
    from app import create_app

    app = create_app(testing=True)
    with app.test_client() as client:
        yield client


def _login(app_client, role):
    response = app_client.post("/api/v1/auth/login", json={"test_id": ROLE_TEST_IDS[role]})
    assert response.status_code == 200
    return response.get_json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_draft_docket(app_client):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, ROLE_TEST_IDS["citizen"], "Vandalism", "Broken window overnight", location="Main St", incident_date="2026-01-01")
    return case["case_reference"]


def _create_and_submit_docket(app_client, citizen_token):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, ROLE_TEST_IDS["citizen"], "Vandalism", "Broken window overnight", location="Main St", incident_date="2026-01-01")
    case_reference = case["case_reference"]
    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        json={"statement_text": "Someone broke my window."},
        headers=_auth_headers(citizen_token),
    )
    app_client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=_auth_headers(citizen_token))
    return case_reference


def _register_docket(app_client, citizen_token, constable_token, case_reference):
    interview_response = app_client.post(f"/api/v1/constable/dockets/{case_reference}/interview", headers=_auth_headers(constable_token))
    interview_id = interview_response.get_json()["interview_id"]
    app_client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        json={"filename": "citizen.wav"},
        headers=_auth_headers(citizen_token),
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        json={"filename": "constable.wav"},
        headers=_auth_headers(constable_token),
    )
    register_response = app_client.post(f"/api/v1/constable/interviews/{interview_id}/register", headers=_auth_headers(constable_token))
    assert register_response.status_code == 200


def _assign_detective(app_client, case_reference, detective_id=ROLE_TEST_IDS["detective"]):
    station_commander_token = _login(app_client, "station_commander")
    response = app_client.post(
        f"/api/v1/station-commander/dockets/{case_reference}/reassign",
        json={"officer_id": detective_id, "reason": "Assigning detective for investigation."},
        headers=_auth_headers(station_commander_token),
    )
    assert response.status_code == 200
    return response.get_json()


class TestDocketListAccessibleToEveryOperationalRole:
    @pytest.mark.parametrize("role", ["constable", "detective", "station_commander", "ipid"])
    def test_list_dockets_not_forbidden(self, app_client, role):
        token = _login(app_client, role)
        response = app_client.get("/api/v1/station-commander/dockets", headers=_auth_headers(token))
        assert response.status_code == 200
        assert isinstance(response.get_json(), list)

    def test_still_forbidden_for_citizen(self, app_client):
        token = _login(app_client, "citizen")
        response = app_client.get("/api/v1/station-commander/dockets", headers=_auth_headers(token))
        assert response.status_code == 403

    def test_detective_dashboard_and_active_cases_page_render_without_forbidden(self, app_client):
        """Full-stack: what the detective dashboard's 'Current Investigations'
        panel and the shared Active Cases page actually depend on."""
        detective_token = _login(app_client, "detective")
        list_response = app_client.get("/api/v1/station-commander/dockets", headers=_auth_headers(detective_token))
        assert list_response.status_code == 200

        page_response = app_client.get("/detective")
        # Unauthenticated page load just redirects; the point is the API call
        # the page's JS makes (asserted above) no longer 403s for this role.
        assert page_response.status_code in (200, 302)


class TestReassignmentTransfersInvestigationOwnership:
    """Only one detective identity is seeded in this dev environment, so the
    real force_reassign_docket()->AssignmentService path (which validates the
    target officer against the identity registry) can't be exercised end to
    end with a *different* second detective here. reassign_active_investigation()
    is tested directly instead, against the real InvestigationService/
    InvestigationRepository -- exactly what force_reassign_docket() calls."""

    def test_reassign_active_investigation_transfers_ownership_to_the_new_detective(self, app_client):
        from app.modules.investigation_engine.services import InvestigationService

        citizen_token = _login(app_client, "citizen")
        constable_token = _login(app_client, "constable")
        case_reference = _create_and_submit_docket(app_client, citizen_token)
        _register_docket(app_client, citizen_token, constable_token, case_reference)
        _assign_detective(app_client, case_reference)

        detective_a_token = _login(app_client, "detective")
        create_investigation = app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/investigation",
            json={"notes": "Initial notes from detective A."},
            headers=_auth_headers(detective_a_token),
        )
        assert create_investigation.status_code == 201
        investigation_id = create_investigation.get_json()["investigation_id"]

        before = app_client.get(f"/api/v1/detective/investigations/{investigation_id}", headers=_auth_headers(detective_a_token))
        assert before.status_code == 200

        with app_client.application.app_context():
            investigation_service = app_client.application.extensions["investigation_service"]
            assert isinstance(investigation_service, InvestigationService)
            investigation_service.reassign_active_investigation(case_reference, "DET-B-9999999999999", "SC-1", reason="Detective A unavailable.")

        # Detective A is now locked out -- this is the flip side of the bug:
        # not transferring ownership left the *old* detective with sole access
        # even though the assignment record says otherwise.
        after_old = app_client.get(f"/api/v1/detective/investigations/{investigation_id}", headers=_auth_headers(detective_a_token))
        assert after_old.status_code == 403

        stored = investigation_service.get_investigation(investigation_id)
        assert stored["detective_id"] == "DET-B-9999999999999"
        assert stored["timeline"][-1]["event_type"] == "investigation_reassigned"

    def test_ipid_reassignment_endpoint_also_wires_up_the_investigation_transfer(self, app_client):
        """IPIDReviewService.reassign_case_officer() hits the same
        AssignmentService.create_replacement_assignment() path as the station
        commander's force_reassign_docket() and needs the identical
        investigation-transfer call -- this was missed on the first pass and
        would have silently reintroduced the "new detective locked out" bug
        via IPID's reassignment endpoint instead. The seeded environment only
        contains one detective, so this uses a simulated second detective ID in
        the identity registry while still asserting the real reassignment path."""
        from unittest.mock import MagicMock

        citizen_token = _login(app_client, "citizen")
        constable_token = _login(app_client, "constable")
        case_reference = _create_and_submit_docket(app_client, citizen_token)
        _register_docket(app_client, citizen_token, constable_token, case_reference)
        _assign_detective(app_client, case_reference)

        detective_token = _login(app_client, "detective")
        create_investigation = app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/investigation",
            json={"notes": "Initial notes."},
            headers=_auth_headers(detective_token),
        )
        assert create_investigation.status_code == 201

        with app_client.application.app_context():
            ipid_service = app_client.application.extensions["ipid_service"]
            original_get_identity = ipid_service.identity_registry.get_identity

            def fake_get_identity(officer_id):
                if str(officer_id) == "DET-B-9999999999999":
                    return {"test_id": "DET-B-9999999999999", "role": "detective", "active": True, "access_state": "ACTIVE"}
                return original_get_identity(str(officer_id))

            ipid_service.identity_registry.get_identity = MagicMock(side_effect=fake_get_identity)
            spy = MagicMock(wraps=ipid_service.investigation_service.reassign_active_investigation)
            ipid_service.investigation_service.reassign_active_investigation = spy

        ipid_token = _login(app_client, "ipid")
        target_officer = "DET-B-9999999999999"
        response = app_client.post(
            f"/api/v1/ipid/dockets/{case_reference}/reassign",
            json={"officer_id": target_officer, "reason": "IPID confirming officer assignment."},
            headers=_auth_headers(ipid_token),
        )
        assert response.status_code == 200
        spy.assert_called_once()
        assert spy.call_args.args[0] == case_reference
        assert spy.call_args.args[1] == target_officer

    def test_is_a_no_op_when_there_is_no_active_investigation(self, app_client):
        from app.modules.investigation_engine.services import InvestigationService

        citizen_token = _login(app_client, "citizen")
        case_reference = _create_and_submit_docket(app_client, citizen_token)

        with app_client.application.app_context():
            investigation_service = app_client.application.extensions["investigation_service"]
            assert isinstance(investigation_service, InvestigationService)
            result = investigation_service.reassign_active_investigation(case_reference, "DET-B-9999999999999", "SC-1")
            assert result is None


class TestConstableCanBeAssignedBeforeRegistration:
    def test_assigning_a_constable_to_an_unregistered_docket_succeeds(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_and_submit_docket(app_client, citizen_token)

        docket_check = app_client.get(f"/api/v1/citizen/dockets/{case_reference}", headers=_auth_headers(citizen_token))
        assert docket_check.get_json()["status"] == "AWAITING_CONSTABLE_REGISTRATION"

        station_commander_token = _login(app_client, "station_commander")
        response = app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["constable"], "reason": "Assigning a constable to take hold of this docket."},
            headers=_auth_headers(station_commander_token),
        )
        assert response.status_code == 200
        assert response.get_json()["officer_role"] == "constable"

    def test_assigning_a_detective_to_an_unregistered_docket_is_rejected(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_and_submit_docket(app_client, citizen_token)

        station_commander_token = _login(app_client, "station_commander")
        response = app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["detective"], "reason": "Should not be allowed pre-registration."},
            headers=_auth_headers(station_commander_token),
        )
        assert response.status_code == 400

    def test_assigning_to_a_draft_docket_is_still_rejected(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_draft_docket(app_client)

        station_commander_token = _login(app_client, "station_commander")
        response = app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["constable"], "reason": "Docket not yet submitted."},
            headers=_auth_headers(station_commander_token),
        )
        assert response.status_code == 400

    def test_officers_endpoint_filters_to_constable_role(self, app_client):
        token = _login(app_client, "station_commander")
        response = app_client.get("/api/v1/station-commander/officers?role=constable", headers=_auth_headers(token))
        assert response.status_code == 200
        officers = response.get_json()
        assert officers and all(officer["role"] == "constable" for officer in officers)
