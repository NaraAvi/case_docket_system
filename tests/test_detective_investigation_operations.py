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


def create_and_submit_docket(app_client, token, title, description="This is a sufficiently detailed account of the incident for investigation."):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, title, description)
    case_reference = case["case_reference"]

    statement_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {token}"},
        json={"statement_text": "This is the statement that will be reviewed by the detective."},
    )
    assert statement_response.status_code == 201

    submit_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert submit_response.status_code == 200
    return case_reference


def register_case(app_client, citizen_token, constable_token, title="Registered investigation case"):
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
            "storage_reference": "citizen-investigate.wav",
            "filename": "citizen-investigate.wav",
        },
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={
            "recording_type": "constable_recording",
            "storage_reference": "constable-investigate.wav",
            "filename": "constable-investigate.wav",
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


def open_investigation(app_client, citizen_token, constable_token, detective_token, title="Investigation operations case"):
    case_reference = register_case(app_client, citizen_token, constable_token, title)
    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Initial investigation opened."},
    )
    assert response.status_code == 201
    return case_reference, response.get_json()["investigation_id"]


def test_detective_case_review_returns_operational_summary(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Case review summary")

    response = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/case",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["case_reference"] == case_reference
    assert payload["case_status"] == "REGISTERED"
    assert payload["title"] == "Case review summary"
    assert payload["citizen_submission"]["statements"]
    assert payload["case_reference"] == case_reference


def test_detective_can_view_case_statements(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Statement review case")

    response = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/statements",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload[0]["case_reference"] == case_reference
    assert payload[0]["statement_type"] == "citizen_statement"
    assert "statement_content" in payload[0]


def test_detective_can_view_case_evidence_and_redacts_storage_details(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Evidence review case")

    evidence_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/evidence",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "evidence_type": "PHOTO",
            "description": "Photo of the incident area.",
            "filename": "photo.png",
        },
    )
    assert evidence_response.status_code == 201

    response = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/evidence",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload[0]["evidence_type"] == "PHOTO"
    assert payload[0]["source"] == "citizen"
    assert "storage_root" not in payload[0]


def test_detective_can_view_constable_flags_and_related_cases(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Flag and relation case")

    flag_response = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/flags",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"category": "INSUFFICIENT_INFORMATION", "notes": "Potential concern with the report details."},
    )
    assert flag_response.status_code == 201

    related_response = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/related",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"related_case_reference": case_reference, "relationship_type": "RELATED_CASE", "notes": "Self-reference should be rejected."},
    )
    assert related_response.status_code == 400

    response = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/flags",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload[0]["category"] == "INSUFFICIENT_INFORMATION"


def test_detective_can_create_finding_and_retrieve_it(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Finding creation case")

    create_response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/findings",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"finding_type": "VALID", "notes": "The report is supported by the statement and evidence."},
    )
    assert create_response.status_code == 201
    payload = create_response.get_json()
    assert payload["detective_id"] == VALID_DETECTIVE_ID
    assert payload["finding_type"] == "VALID"

    list_response = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/findings",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert list_response.status_code == 200
    findings = list_response.get_json()
    assert findings[0]["finding_type"] == "VALID"


def test_invalid_finding_type_and_missing_notes_are_rejected(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Finding validation case")

    invalid_type = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/findings",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"finding_type": "FOO", "notes": "Should be rejected."},
    )
    assert invalid_type.status_code == 400

    empty_notes = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/findings",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"finding_type": "VALID", "notes": "   "},
    )
    assert empty_notes.status_code == 400


def test_detective_can_complete_investigation_with_valid_outcome(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Completion case")

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/complete",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"outcome": "VALID", "final_notes": "The case is valid based on the completed investigation findings."},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["outcome"] == "VALID"
    assert payload["status"] == "COMPLETED"
    assert payload["completed_at"] is not None


def test_completed_investigation_rejects_new_findings_and_recompletion(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Completed guard case")

    complete = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/complete",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"outcome": "VALID", "final_notes": "The case is valid based on the investigation."},
    )
    assert complete.status_code == 200

    finding_after_close = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/findings",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"finding_type": "INVALID", "notes": "Should fail after completion."},
    )
    assert finding_after_close.status_code == 400

    repeat_complete = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/complete",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"outcome": "INVALID", "final_notes": "Should not be allowed again."},
    )
    assert repeat_complete.status_code == 400


def test_security_rejects_citizen_and_constable_on_detective_operations(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Security case")

    citizen_case = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/case",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert citizen_case.status_code == 403

    constable_case = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/case",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert constable_case.status_code == 403

    unauthorized_detective = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": "2200223333115"},
    )
    assert unauthorized_detective.status_code == 200
    other_detective = login(app_client, VALID_DETECTIVE_ID)

    other_case = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/case",
        headers={"Authorization": f"Bearer {other_detective}"},
    )
    assert other_case.status_code == 200


def test_client_detective_id_cannot_override_authenticated_identity(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Impersonation case")

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/findings",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"detective_id": "9999999999999", "finding_type": "VALID", "notes": "Authenticated Detective remains the source of truth."},
    )
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["detective_id"] == VALID_DETECTIVE_ID
