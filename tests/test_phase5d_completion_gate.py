import pytest

VALID_CITIZEN_ID = "2200223333111"
VALID_CONSTABLE_ID = "2200223333114"
VALID_DETECTIVE_ID = "2200223333115"


def login(app_client, test_id):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": test_id},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def create_and_submit_docket(app_client, token, title):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, title, "Phase 5D completion gate test case")
    case_reference = case["case_reference"]
    statement_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {token}"},
        json={"statement_text": "This is the statement that will be reviewed."},
    )
    assert statement_response.status_code == 201
    submit_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert submit_response.status_code == 200
    return case_reference


def register_case(app_client, citizen_token, constable_token, title="Registered completion gate case"):
    case_reference = create_and_submit_docket(app_client, citizen_token, title)
    interview_response = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/interview",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"status": "STARTED"},
    )
    assert interview_response.status_code == 201
    interview_id = interview_response.get_json()["interview_id"]
    app_client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "recording_type": "citizen_recording",
            "storage_reference": "citizen-completion.wav",
            "filename": "citizen-completion.wav",
        },
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={
            "recording_type": "constable_recording",
            "storage_reference": "constable-completion.wav",
            "filename": "constable-completion.wav",
        },
    )
    register_response = app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/register",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert register_response.status_code == 200
    from tests.conftest import assign_detective_to_case

    assign_detective_to_case(app_client, case_reference, VALID_DETECTIVE_ID)
    return case_reference


@pytest.fixture()
def citizen_token(app_client):
    return login(app_client, VALID_CITIZEN_ID)


@pytest.fixture()
def constable_token(app_client):
    return login(app_client, VALID_CONSTABLE_ID)


@pytest.fixture()
def detective_token(app_client):
    return login(app_client, VALID_DETECTIVE_ID)


def test_completion_requires_active_assignment_and_ignores_client_forgery(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Assignment gate case")
    assignment_service = app_client.application.extensions["assignment_service"]
    assignment = assignment_service.get_current_assignment_for_case(case_reference)
    assignment_service.end_assignment(assignment["assignment_id"], ended_by=VALID_DETECTIVE_ID, ended_by_role="detective", reason="forced end for gate test")

    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "This should fail because the assignment has ended."},
    )
    assert response.status_code == 400

    investigation_response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Open a new investigation after assignment ends."},
    )
    assert investigation_response.status_code == 400


def test_status_patch_cannot_complete_investigation_directly(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Status bypass case")
    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Initial investigation opened."},
    )
    investigation_id = response.get_json()["investigation_id"]

    patch_response = app_client.patch(
        f"/api/v1/detective/investigations/{investigation_id}/status",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"status": "COMPLETED", "detective_id": "9999999999999"},
    )
    assert patch_response.status_code == 400


def test_completion_audit_records_previous_and_new_state(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Audit completion case")
    investigation_id = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Initial investigation opened."},
    ).get_json()["investigation_id"]

    complete_response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/complete",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"outcome": "VALID", "final_notes": "The evidence supports the account."},
    )
    assert complete_response.status_code == 200

    audit_events = app_client.application.extensions["audit_service"].get_for_case(case_reference)
    assert any(event.get("action") == "detective_investigation_completed" for event in audit_events)
    event = next(event for event in audit_events if event.get("action") == "detective_investigation_completed")
    assert event.get("previous_state") in {"OPEN", "IN_PROGRESS"}
    assert event.get("new_state") == "COMPLETED"
