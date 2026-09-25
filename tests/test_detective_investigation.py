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


def create_and_submit_docket(
    app_client,
    token,
    title,
    description="This is a sufficiently detailed account of the incident for review.",
):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, title, description)
    case_reference = case["case_reference"]

    statement_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {token}"},
        json={"statement_text": "This is the statement I am submitting for detective review."},
    )
    assert statement_response.status_code == 201

    submit_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert submit_response.status_code == 200
    return case_reference


def register_case(app_client, citizen_token, constable_token, title="Registered case"):
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
            "storage_reference": "citizen-register.wav",
            "filename": "citizen-register.wav",
        },
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={
            "recording_type": "constable_recording",
            "storage_reference": "constable-register.wav",
            "filename": "constable-register.wav",
        },
    )

    register = app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/register",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert register.status_code == 200

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


def test_detective_test_identity_can_authenticate(app_client):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_DETECTIVE_ID},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["role"] == "detective"
    assert payload["test_id"] == VALID_DETECTIVE_ID


def test_detective_jwt_contains_detective_role(app_client):
    token = login(app_client, VALID_DETECTIVE_ID)
    response = app_client.get(
        "/api/v1/detective/dockets/does-not-matter",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in {400, 404}


def test_citizen_cannot_access_detective_endpoints(app_client, citizen_token):
    response = app_client.get(
        "/api/v1/detective/dockets/not-a-case",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert response.status_code == 403


def test_constable_cannot_access_detective_endpoints(app_client, constable_token):
    response = app_client.get(
        "/api/v1/detective/dockets/not-a-case",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert response.status_code == 403


def test_unauthenticated_access_to_detective_endpoints_is_rejected(app_client):
    response = app_client.get("/api/v1/detective/dockets/not-a-case")
    assert response.status_code == 401


def test_detective_can_access_registered_docket(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Detective review case")

    response = app_client.get(
        f"/api/v1/detective/dockets/{case_reference}",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["case_reference"] == case_reference
    assert payload["status"] == "REGISTERED"


def test_detective_cannot_access_draft_docket(app_client, citizen_token, detective_token):
    case_reference = create_and_submit_docket(app_client, citizen_token, "Draft detective blocked case")
    response = app_client.get(
        f"/api/v1/detective/dockets/{case_reference}",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 400


def test_detective_cannot_access_awaiting_constable_registration_docket(app_client, citizen_token, detective_token):
    case_reference = create_and_submit_docket(app_client, citizen_token, "Awaiting registration case")
    response = app_client.get(
        f"/api/v1/detective/dockets/{case_reference}",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 400


def test_detective_nonexistent_docket_returns_error(app_client, detective_token):
    response = app_client.get(
        "/api/v1/detective/dockets/NO_SUCH_CASE",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 404


def test_detective_can_create_investigation(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Investigation creation case")

    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Initial investigation start."},
    )
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["case_reference"] == case_reference
    assert payload["detective_id"] == VALID_DETECTIVE_ID
    assert payload["status"] == "OPEN"
    assert payload["investigation_id"].startswith("INV-")


def test_detective_investigation_has_unique_id_and_links_case(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Unique investigation case")

    first = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "First investigation."},
    )
    second = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Duplicate attempt."},
    )

    assert first.status_code == 201
    assert second.status_code == 400
    assert first.get_json()["investigation_id"] != ""
    assert first.get_json()["case_reference"] == case_reference


def test_detective_investigation_records_authenticated_detective(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Detective auth case")

    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"detective_id": "9999999999999", "notes": "Client supplied detective id should be ignored."},
    )
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["detective_id"] == VALID_DETECTIVE_ID


def test_duplicate_active_investigation_is_rejected(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Duplicate warning case")

    first = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Initial investigation."},
    )
    assert first.status_code == 201

    second = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Duplicate active investigation."},
    )
    assert second.status_code == 400


def test_detective_can_retrieve_investigation(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Retrieve investigation case")

    created = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Investigation should be retrievable."},
    )
    investigation_id = created.get_json()["investigation_id"]

    response = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["investigation_id"] == investigation_id
    assert payload["case_reference"] == case_reference
    assert payload["status"] == "OPEN"


def test_detective_status_transition_open_to_in_progress(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Status transition case")

    created = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Open investigation for change."},
    )
    investigation_id = created.get_json()["investigation_id"]

    response = app_client.patch(
        f"/api/v1/detective/investigations/{investigation_id}/status",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"status": "IN_PROGRESS"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "IN_PROGRESS"


def test_detective_status_transition_in_progress_to_completed(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Completed status case")

    created = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Investigation moving to completion."},
    )
    investigation_id = created.get_json()["investigation_id"]

    app_client.patch(
        f"/api/v1/detective/investigations/{investigation_id}/status",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"status": "IN_PROGRESS"},
    )
    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/complete",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"outcome": "VALID", "final_notes": "The evidence supports the conclusion."},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "COMPLETED"


def test_invalid_status_rejected(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Invalid status case")

    created = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Invalid status attempt."},
    )
    investigation_id = created.get_json()["investigation_id"]

    response = app_client.patch(
        f"/api/v1/detective/investigations/{investigation_id}/status",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"status": "INVALID"},
    )
    assert response.status_code == 400


def test_completed_investigation_cannot_reopen(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Completed reopen case")

    created = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Investigation to close."},
    )
    investigation_id = created.get_json()["investigation_id"]

    app_client.patch(
        f"/api/v1/detective/investigations/{investigation_id}/status",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"status": "IN_PROGRESS"},
    )
    app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/complete",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"outcome": "VALID", "final_notes": "The evidence supports the conclusion."},
    )

    reopen = app_client.patch(
        f"/api/v1/detective/investigations/{investigation_id}/status",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"status": "IN_PROGRESS"},
    )
    assert reopen.status_code == 400


def test_citizen_cannot_create_investigation(app_client, citizen_token, constable_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Citizen investigation denial case")
    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"notes": "Citizen should be rejected."},
    )
    assert response.status_code == 403


def test_constable_cannot_create_investigation(app_client, citizen_token, constable_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Constable investigation denial case")
    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"notes": "Constable should be rejected."},
    )
    assert response.status_code == 403


def test_investigation_creation_creates_audit_event(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Audit case")

    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Audit should be created."},
    )
    assert response.status_code == 201

    audit = app_client.get(
        "/api/v1/citizen/dockets",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert audit.status_code == 200


def test_investigation_status_transition_creates_audit_event(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, title="Status audit case")

    created = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Audit status change."},
    )
    investigation_id = created.get_json()["investigation_id"]

    response = app_client.patch(
        f"/api/v1/detective/investigations/{investigation_id}/status",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"status": "IN_PROGRESS"},
    )
    assert response.status_code == 200
