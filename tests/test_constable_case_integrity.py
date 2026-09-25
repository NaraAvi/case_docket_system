import pytest

VALID_CITIZEN_ID = "2200223333111"
VALID_CONSTABLE_ID = "2200223333114"


def create_and_submit_docket(app_client, token, title, description="Test case for review"):
    from tests.conftest import create_case_via_service

    citizen_id = "2200223333111"
    case = create_case_via_service(app_client, citizen_id, title, description)
    case_reference = case["case_reference"]

    statement_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {token}"},
        json={"statement_text": "This is the statement I am submitting for review."},
    )
    assert statement_response.status_code == 201

    submit_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert submit_response.status_code == 200
    return case_reference


def test_constable_can_create_invalidity_flag(app_client):
    citizen_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    constable_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )
    citizen_token = citizen_response.get_json()["access_token"]
    constable_token = constable_response.get_json()["access_token"]

    case_reference = create_and_submit_docket(
        app_client,
        citizen_token,
        "Flag review docket",
        "This docket should allow a constable review flag.",
    )

    response = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/flags",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={
            "category": "INCONSISTENT_INFORMATION",
            "notes": "The citizen statement appears inconsistent with the location details.",
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["case_reference"] == case_reference
    assert payload["category"] == "INCONSISTENT_INFORMATION"
    assert payload["status"] == "OPEN"
    assert payload["created_by"] == VALID_CONSTABLE_ID


def test_invalid_flag_category_and_missing_note_are_rejected(app_client):
    citizen_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    constable_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )
    citizen_token = citizen_response.get_json()["access_token"]
    constable_token = constable_response.get_json()["access_token"]

    case_reference = create_and_submit_docket(
        app_client,
        citizen_token,
        "Invalid flag category case",
        "This docket should reject invalid flag input.",
    )

    invalid_category = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/flags",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"category": "NOT_A_REAL_CATEGORY", "notes": "This should fail."},
    )
    assert invalid_category.status_code == 400

    missing_note = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/flags",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"category": "OTHER"},
    )
    assert missing_note.status_code == 400


def test_citizen_cannot_create_or_update_flag(app_client):
    citizen_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    constable_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )
    citizen_token = citizen_response.get_json()["access_token"]
    constable_token = constable_response.get_json()["access_token"]

    case_reference = create_and_submit_docket(
        app_client,
        citizen_token,
        "Citizen flag denial case",
        "The citizen should not be able to create a constable flag.",
    )

    create_flag = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/flags",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"category": "OTHER", "notes": "Citizen attempted to add a flag."},
    )
    assert create_flag.status_code == 403

    # constable-created flag for later update test
    created_flag = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/flags",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"category": "OTHER", "notes": "Operational concern requiring review."},
    )
    assert created_flag.status_code == 201
    flag_id = created_flag.get_json()["flag_id"]

    update_by_citizen = app_client.patch(
        f"/api/v1/constable/flags/{flag_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"status": "RESOLVED", "notes": "Citizen should not be allowed to change this."},
    )
    assert update_by_citizen.status_code == 403


def test_flag_does_not_change_docket_status_or_access(app_client):
    citizen_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    constable_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )
    citizen_token = citizen_response.get_json()["access_token"]
    constable_token = constable_response.get_json()["access_token"]

    case_reference = create_and_submit_docket(
        app_client,
        citizen_token,
        "Flag status guard case",
        "The flag should not close or freeze the docket.",
    )

    flag_response = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/flags",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"category": "OTHER", "notes": "This is just a review concern."},
    )
    assert flag_response.status_code == 201

    docket_response = app_client.get(
        f"/api/v1/citizen/dockets/{case_reference}",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert docket_response.status_code == 200
    docket = docket_response.get_json()
    assert docket["status"] == "AWAITING_CONSTABLE_REGISTRATION"

    patch_response = app_client.patch(
        f"/api/v1/constable/flags/{flag_response.get_json()['flag_id']}",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"status": "RESOLVED", "notes": "After review, concern was closed."},
    )
    assert patch_response.status_code == 200
    assert patch_response.get_json()["status"] == "RESOLVED"


def test_constable_can_search_dockets_and_citizen_is_denied(app_client):
    citizen_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    constable_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )
    citizen_token = citizen_response.get_json()["access_token"]
    constable_token = constable_response.get_json()["access_token"]

    case_reference = create_and_submit_docket(
        app_client,
        citizen_token,
        "Searchable related docket example",
        "Search should find this case by title and description text.",
    )

    search_response = app_client.get(
        "/api/v1/constable/dockets/search",
        headers={"Authorization": f"Bearer {constable_token}"},
        query_string={"q": "Searchable related docket"},
    )
    assert search_response.status_code == 200
    payload = search_response.get_json()
    assert isinstance(payload, list)
    assert any(item["case_reference"] == case_reference for item in payload)
    assert all("citizen_id" not in item for item in payload)

    citizen_search = app_client.get(
        "/api/v1/constable/dockets/search",
        headers={"Authorization": f"Bearer {citizen_token}"},
        query_string={"q": "Searchable related docket"},
    )
    assert citizen_search.status_code == 403


def test_constable_docket_includes_protected_submission_source_context(app_client):
    citizen_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    constable_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )
    citizen_token = citizen_response.get_json()["access_token"]
    constable_token = constable_response.get_json()["access_token"]

    submission_response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Protected source continuity case",
            "description": "Witness narrative and harm details are reported by the citizen.",
            "incident_date": "2026-09-20",
            "location": "Station Gate",
            "reporter_relationship": "Witness",
            "people": [{"person_number": 1, "reported_roles": ["Witness"], "name": "Alice Example"}],
            "harm": {"reported": True, "types": ["EMOTIONAL"], "description": "Distress and fear."},
            "current_safety": {"current_safety_answer": "AFTER_EVENT_SAFE", "risk_types": ["NONE"], "safety_narrative": "The witness is safe."},
        },
    )
    assert submission_response.status_code == 201
    submission_id = submission_response.get_json()["submission_id"]

    assertion_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "I saw the officer at the station gate."},
    )
    assert assertion_response.status_code == 201
    assertion_id = assertion_response.get_json()["assertion_id"]

    claim_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}/claims",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert claim_response.status_code == 201

    analysis_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert analysis_response.status_code == 201
    candidate_id = analysis_response.get_json()["candidate"]["candidate_id"]

    create_case_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/incident-candidates/{candidate_id}/create-case",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert create_case_response.status_code == 200
    case_reference = create_case_response.get_json()["case_reference"]

    docket_response = app_client.get(
        f"/api/v1/constable/dockets/{case_reference}",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert docket_response.status_code == 200
    payload = docket_response.get_json()
    assert payload["source_submission_id"] == submission_id
    assert payload["source_candidate_id"] == candidate_id
    assert payload["citizen_submission"]["submission_id"] == submission_id
    assert payload["citizen_submission"]["original_content"]["reporter_relationship"] == "Witness"
    assert payload["citizen_assertions"][0]["assertion_text"] == "I saw the officer at the station gate."
    assert payload["citizen_claims"]
    assert payload["incident_candidate"]["candidate_id"] == candidate_id
    assert payload["relationships"]
    assert payload["citizen_evidence"] == []


def test_constable_can_link_dockets_and_reject_invalid_duplicates(app_client):
    citizen_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    constable_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )
    citizen_token = citizen_response.get_json()["access_token"]
    constable_token = constable_response.get_json()["access_token"]

    case_a = create_and_submit_docket(
        app_client,
        citizen_token,
        "Link source case",
        "This is the first docket in a related-case test.",
    )
    case_b = create_and_submit_docket(
        app_client,
        citizen_token,
        "Link related case",
        "This is the second docket in a related-case test.",
    )

    create_link = app_client.post(
        f"/api/v1/constable/dockets/{case_a}/related",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"related_case_reference": case_b, "relationship_type": "RELATED_CASE", "notes": "Shared incident context."},
    )
    assert create_link.status_code == 201
    payload = create_link.get_json()
    assert payload["source_case_reference"] == case_a
    assert payload["related_case_reference"] == case_b
    assert payload["relationship_type"] == "RELATED_CASE"
    assert payload["created_by"] == VALID_CONSTABLE_ID
    assert payload["created_at"]

    list_source = app_client.get(
        f"/api/v1/constable/dockets/{case_a}/related",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert list_source.status_code == 200
    source_items = list_source.get_json()
    assert any(item["related_case_reference"] == case_b for item in source_items)

    list_related = app_client.get(
        f"/api/v1/constable/dockets/{case_b}/related",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert list_related.status_code == 200
    related_items = list_related.get_json()
    assert any(item["source_case_reference"] == case_a for item in related_items)

    duplicate = app_client.post(
        f"/api/v1/constable/dockets/{case_a}/related",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"related_case_reference": case_b, "relationship_type": "RELATED_CASE", "notes": "Duplicate."},
    )
    assert duplicate.status_code == 400

    reverse_duplicate = app_client.post(
        f"/api/v1/constable/dockets/{case_b}/related",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"related_case_reference": case_a, "relationship_type": "RELATED_CASE", "notes": "Reverse duplicate."},
    )
    assert reverse_duplicate.status_code == 400

    self_link = app_client.post(
        f"/api/v1/constable/dockets/{case_a}/related",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"related_case_reference": case_a, "relationship_type": "RELATED_CASE", "notes": "Self link is not allowed."},
    )
    assert self_link.status_code == 400

    citizen_link = app_client.post(
        f"/api/v1/constable/dockets/{case_a}/related",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"related_case_reference": case_b, "relationship_type": "RELATED_CASE", "notes": "Citizen attempted link."},
    )
    assert citizen_link.status_code == 403


def test_open_docket_rejects_non_waiting_cases(app_client):
    citizen_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    constable_response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )
    citizen_token = citizen_response.get_json()["access_token"]
    constable_token = constable_response.get_json()["access_token"]

    case_reference = create_and_submit_docket(
        app_client,
        citizen_token,
        "Open docket status validation",
        "This docket should be reviewable only while awaiting constable registration.",
    )
    constable_open = app_client.get(
        f"/api/v1/constable/dockets/{case_reference}",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert constable_open.status_code == 200

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
            "storage_reference": "citizen-validation.wav",
            "filename": "citizen-validation.wav",
        },
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={
            "recording_type": "constable_recording",
            "storage_reference": "constable-validation.wav",
            "filename": "constable-validation.wav",
        },
    )
    register_response = app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/register",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert register_response.status_code == 200

    re_open = app_client.get(
        f"/api/v1/constable/dockets/{case_reference}",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert re_open.status_code == 400
