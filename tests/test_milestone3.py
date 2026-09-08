"""Tests for Milestone 3: template finalization and interactive UX completion.

Covers the two small backend additions this milestone needed (investigation
notes update, station-commander officer listing) plus full-stack smoke tests
confirming every reworked detail/dashboard template still renders through the
real Flask app after the Jinja macro and JS-wiring changes.
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
    token = response.get_json()["access_token"]
    app_client.set_cookie("pdas_session_token", token, path="/")
    return token


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _build_registered_case(app_client):
    """Walk a docket through citizen submission -> constable registration.

    Returns the case_reference of a REGISTERED docket, ready for a detective
    to open an investigation against.
    """
    citizen_token = _login(app_client, "citizen")
    create_response = app_client.post(
        "/api/v1/citizen/dockets",
        json={"title": "Vandalism", "description": "Broken window", "location": "Main St", "incident_date": "2026-01-01"},
        headers=_auth_headers(citizen_token),
    )
    assert create_response.status_code == 201
    case_reference = create_response.get_json()["case_reference"]

    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        json={"statement_text": "Someone broke my window overnight."},
        headers=_auth_headers(citizen_token),
    )
    submit_response = app_client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=_auth_headers(citizen_token))
    assert submit_response.status_code == 200

    constable_token = _login(app_client, "constable")
    app_client.get(f"/api/v1/constable/dockets/{case_reference}", headers=_auth_headers(constable_token))
    interview_response = app_client.post(f"/api/v1/constable/dockets/{case_reference}/interview", headers=_auth_headers(constable_token))
    interview_id = interview_response.get_json()["interview_id"]

    app_client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        json={"recording_type": "citizen_recording", "filename": "citizen.wav"},
        headers=_auth_headers(citizen_token),
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        json={"recording_type": "constable_recording", "filename": "constable.wav"},
        headers=_auth_headers(constable_token),
    )
    register_response = app_client.post(f"/api/v1/constable/interviews/{interview_id}/register", headers=_auth_headers(constable_token))
    assert register_response.status_code == 200
    assert register_response.get_json()["status"] == "REGISTERED"
    return case_reference


class TestInvestigationNotesEndpoint:
    def test_detective_can_update_notes_and_it_persists(self, app_client):
        case_reference = _build_registered_case(app_client)
        detective_token = _login(app_client, "detective")

        create_response = app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/investigation",
            json={"notes": "Initial notes."},
            headers=_auth_headers(detective_token),
        )
        assert create_response.status_code == 201
        investigation_id = create_response.get_json()["investigation_id"]

        update_response = app_client.patch(
            f"/api/v1/detective/investigations/{investigation_id}/notes",
            json={"notes": "Updated after canvassing witnesses."},
            headers=_auth_headers(detective_token),
        )
        assert update_response.status_code == 200
        assert update_response.get_json()["notes"] == "Updated after canvassing witnesses."

        docket_response = app_client.get(f"/api/v1/detective/dockets/{case_reference}", headers=_auth_headers(detective_token))
        assert docket_response.get_json()["investigation"]["notes"] == "Updated after canvassing witnesses."

    def test_empty_notes_rejected(self, app_client):
        case_reference = _build_registered_case(app_client)
        detective_token = _login(app_client, "detective")
        create_response = app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/investigation",
            json={"notes": "Initial notes."},
            headers=_auth_headers(detective_token),
        )
        investigation_id = create_response.get_json()["investigation_id"]

        response = app_client.patch(
            f"/api/v1/detective/investigations/{investigation_id}/notes",
            json={"notes": "   "},
            headers=_auth_headers(detective_token),
        )
        assert response.status_code == 400

    def test_forbidden_for_non_detective_role(self, app_client):
        constable_token = _login(app_client, "constable")
        response = app_client.patch(
            "/api/v1/detective/investigations/INV-000001/notes",
            json={"notes": "Should not work."},
            headers=_auth_headers(constable_token),
        )
        assert response.status_code == 403

    def test_404_for_unknown_investigation(self, app_client):
        detective_token = _login(app_client, "detective")
        response = app_client.patch(
            "/api/v1/detective/investigations/INV-999999/notes",
            json={"notes": "Notes for a case that doesn't exist."},
            headers=_auth_headers(detective_token),
        )
        assert response.status_code == 404


class TestStationCommanderOfficersEndpoint:
    def test_lists_constables_and_detectives_by_default(self, app_client):
        token = _login(app_client, "station_commander")
        response = app_client.get("/api/v1/station-commander/officers", headers=_auth_headers(token))
        assert response.status_code == 200
        roles = {officer["role"] for officer in response.get_json()}
        assert roles == {"constable", "detective"}

    def test_filters_by_role(self, app_client):
        token = _login(app_client, "station_commander")
        response = app_client.get("/api/v1/station-commander/officers?role=detective", headers=_auth_headers(token))
        assert response.status_code == 200
        officers = response.get_json()
        assert all(officer["role"] == "detective" for officer in officers)
        assert len(officers) == 1

    def test_rejects_invalid_role(self, app_client):
        token = _login(app_client, "station_commander")
        response = app_client.get("/api/v1/station-commander/officers?role=citizen", headers=_auth_headers(token))
        assert response.status_code == 400

    def test_forbidden_for_non_station_commander(self, app_client):
        token = _login(app_client, "constable")
        response = app_client.get("/api/v1/station-commander/officers", headers=_auth_headers(token))
        assert response.status_code == 403


class TestActiveCasesAndEvidenceVaultUseTheRealRole:
    """Regression test for a pre-existing bug found during the Milestone 3 audit:
    these two routes always rendered role="station_commander" regardless of who
    was actually logged in, so a constable/detective/ipid user got the station
    commander's sidebar nav on these two pages."""

    @pytest.mark.parametrize("role", ["constable", "detective", "station_commander", "ipid"])
    def test_active_cases_reflects_the_logged_in_role(self, app_client, role):
        _login(app_client, role)
        response = app_client.get("/active-cases")
        assert response.status_code == 200
        assert f'data-role="{role}"' in response.get_data(as_text=True)

    @pytest.mark.parametrize("role", ["constable", "detective", "station_commander", "ipid"])
    def test_evidence_vault_reflects_the_logged_in_role(self, app_client, role):
        _login(app_client, role)
        response = app_client.get("/evidence-vault")
        assert response.status_code == 200
        assert f'data-role="{role}"' in response.get_data(as_text=True)


class TestReworkedDetailTemplatesRender:
    """Every detail page was rewritten to use the new components/ macros and
    JS wiring in this milestone -- confirm they still render through the real
    Flask/Jinja stack rather than only trusting the JS test suite."""

    def test_constable_docket_review_renders(self, app_client):
        case_reference = _build_registered_case(app_client)
        _login(app_client, "constable")
        response = app_client.get(f"/constable/dockets/{case_reference}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "flagModal" in html
        assert "CAS-2023-BB1" not in html

    def test_detective_case_workspace_renders(self, app_client):
        case_reference = _build_registered_case(app_client)
        _login(app_client, "detective")
        response = app_client.get(f"/detective/dockets/{case_reference}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "findingModal" in html
        assert "saveInvestigationNote" in html

    def test_station_commander_docket_detail_renders(self, app_client):
        case_reference = _build_registered_case(app_client)
        _login(app_client, "station_commander")
        response = app_client.get(f"/station-commander/dockets/{case_reference}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "targetOfficerSelect" in html
        assert "Detective One" not in html

    def test_ipid_escalation_detail_renders(self, app_client):
        case_reference = _build_registered_case(app_client)
        citizen_token = _login(app_client, "citizen")
        escalation_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "Officer refused to log evidence."},
            headers=_auth_headers(citizen_token),
        )
        assert escalation_response.status_code == 201
        escalation_id = escalation_response.get_json()["escalation_id"]

        _login(app_client, "ipid")
        response = app_client.get(f"/ipid/escalations/{escalation_id}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "dismissEscalationBtn" in html
        assert "data-open-reauth" in html

    def test_nav_marks_the_current_page_active(self, app_client):
        _login(app_client, "constable")
        response = app_client.get("/active-cases")
        html = response.get_data(as_text=True)
        assert '<a class="nav-item active" href="/active-cases">Active Cases</a>' in html
