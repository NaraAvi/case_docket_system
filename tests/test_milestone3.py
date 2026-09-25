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


def _create_draft_docket(app_client, title="Vandalism", description="Broken window overnight", location="Main St", incident_date="2026-01-01"):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(
        app_client,
        ROLE_TEST_IDS["citizen"],
        title,
        description,
        location=location,
        incident_date=incident_date,
    )
    return case["case_reference"]


def _build_registered_case(app_client):
    """Walk a docket through the protected intake boundary and constable registration.

    Returns the case_reference of a REGISTERED docket, ready for a detective
    to open an investigation against.
    """
    from tests.conftest import assign_detective_to_case

    citizen_token = _login(app_client, "citizen")
    case_reference = _create_draft_docket(app_client)
    case = app_client.application.extensions["case_service"].get_case(case_reference)
    case.setdefault("statements", []).append(
        {
            "statement_id": 1,
            "case_reference": case_reference,
            "citizen_id": ROLE_TEST_IDS["citizen"],
            "statement_text": "Someone broke my window overnight.",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    case["status"] = "AWAITING_CONSTABLE_REGISTRATION"
    case["submitted_at"] = "2026-01-01T00:00:00+00:00"
    case["submitted_statement_snapshot"] = [
        {
            "statement_id": 1,
            "citizen_id": ROLE_TEST_IDS["citizen"],
            "statement_text": "Someone broke my window overnight.",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    case["statement_lock_status"] = "LOCKED"
    app_client.application.extensions["case_service"].update_case(case)

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

    assign_detective_to_case(app_client, case_reference, ROLE_TEST_IDS["detective"])
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


class TestCitizenFlowIsFullyOperational:
    """Regression tests for a bug reported after manual end-to-end testing:
    the citizen docket detail page never wired up adding a statement, adding
    evidence, or the final submit-for-review action (nor the "Escalate Case"
    button), even though the backend has supported all of it since Milestone
    1. That silently blocked every downstream role, since no docket could
    ever leave DRAFT status through the UI."""

    def test_full_citizen_journey_create_statement_evidence_submit_escalate(self, app_client):
        citizen_token = _login(app_client, "citizen")
        headers = _auth_headers(citizen_token)

        case_reference = _create_draft_docket(app_client)
        assert app_client.application.extensions["case_service"].get_case(case_reference)["status"] == "DRAFT"

        # A fresh DRAFT docket cannot be submitted without a statement.
        premature_submit = app_client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=headers)
        assert premature_submit.status_code == 400

        statement_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/statements",
            json={"statement_text": "Someone broke my window overnight."},
            headers=headers,
        )
        assert statement_response.status_code == 201

        evidence_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "PHOTO", "filename": "window.jpg", "description": "Photo of the broken window."},
            headers=headers,
        )
        assert evidence_response.status_code == 201

        submit_response = app_client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=headers)
        assert submit_response.status_code == 200
        assert submit_response.get_json()["status"] == "AWAITING_CONSTABLE_REGISTRATION"

        docket_response = app_client.get(f"/api/v1/citizen/dockets/{case_reference}", headers=headers)
        docket = docket_response.get_json()
        assert len(docket["statements"]) == 1
        assert len(docket["evidence"]) == 1

        escalation_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "UNLAWFUL_DELAY", "description": "The constable took too long to register this."},
            headers=headers,
        )
        assert escalation_response.status_code == 201

    def test_docket_detail_page_renders_statement_evidence_and_submit_controls(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_draft_docket(app_client)

        response = app_client.get(f"/citizen/dockets/{case_reference}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "citizenStatementText" in html
        assert "saveCitizenStatement" in html
        assert "addCitizenEvidence" in html
        assert "submitCitizenDocketForReview" in html
        assert "escalateModal" in html

    def test_docket_form_page_no_longer_has_decorative_evidence_and_victim_fields(self, app_client):
        _login(app_client, "citizen")
        response = app_client.get("/citizen/dockets/new")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        # These were static, unwired, and their values were silently discarded on submit.
        assert "Jane Doe" not in html
        assert "victims-box" not in html
        assert 'value="Theft / Property Damage"' not in html


class TestInterviewRecordingFlowIsFullyOperational:
    """Regression tests for a bug reported after manual end-to-end testing:
    "Continue to Interview" started an interview server-side (that part
    always worked) but the constable review page had no UI at all for either
    party to submit a recording or for the constable to register the docket
    afterward -- so clicking it appeared to do nothing. Neither the
    constable_docket_review.html nor citizen_docket_detail.html template had
    ever had an interview panel."""

    def test_constable_review_page_has_the_interview_panel_markup(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_draft_docket(app_client)
        app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/statements",
            json={"statement_text": "Someone broke my window."},
            headers=_auth_headers(citizen_token),
        )
        app_client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=_auth_headers(citizen_token))

        _login(app_client, "constable")
        response = app_client.get(f"/constable/dockets/{case_reference}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "constableInterviewPanel" in html
        assert "submitConstableRecording" in html
        assert "registerDocketBtn" in html

    def test_citizen_detail_page_has_the_interview_panel_markup(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_draft_docket(app_client)

        response = app_client.get(f"/citizen/dockets/{case_reference}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "citizenInterviewPanel" in html
        assert "submitCitizenRecording" in html

    def test_full_interview_pipeline_matches_what_the_ui_now_calls(self, app_client):
        """Exercises the exact request shape the new JS sends (POST with
        just {filename}, no explicit recording_type) end-to-end through to a
        REGISTERED docket, then confirms the constable's docket-scoped
        endpoint correctly rejects it afterward (which is why the Register
        button now redirects to the dashboard instead of back to this page)."""
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_draft_docket(app_client)
        app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/statements",
            json={"statement_text": "Someone broke my window."},
            headers=_auth_headers(citizen_token),
        )
        app_client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=_auth_headers(citizen_token))

        constable_token = _login(app_client, "constable")
        interview_response = app_client.post(
            f"/api/v1/constable/dockets/{case_reference}/interview", headers=_auth_headers(constable_token)
        )
        assert interview_response.status_code == 201
        interview_id = interview_response.get_json()["interview_id"]

        citizen_recording = app_client.post(
            f"/api/v1/citizen/interviews/{interview_id}/recording",
            json={"filename": "citizen.wav"},
            headers=_auth_headers(citizen_token),
        )
        assert citizen_recording.status_code == 201
        assert citizen_recording.get_json()["recording_type"] == "citizen_recording"

        constable_recording = app_client.post(
            f"/api/v1/constable/interviews/{interview_id}/recording",
            json={"filename": "constable.wav"},
            headers=_auth_headers(constable_token),
        )
        assert constable_recording.status_code == 201
        assert constable_recording.get_json()["recording_type"] == "constable_recording"

        interview_status = app_client.get(f"/api/v1/constable/interviews/{interview_id}", headers=_auth_headers(constable_token))
        assert interview_status.get_json()["status"] == "COMPLETED"

        register_response = app_client.post(f"/api/v1/constable/interviews/{interview_id}/register", headers=_auth_headers(constable_token))
        assert register_response.status_code == 200
        assert register_response.get_json()["status"] == "REGISTERED"

        # Confirms the redirect-to-dashboard fix was necessary: the docket-scoped
        # constable endpoint really does reject a docket once it's REGISTERED.
        post_register_docket = app_client.get(f"/api/v1/constable/dockets/{case_reference}", headers=_auth_headers(constable_token))
        assert post_register_docket.status_code == 400
