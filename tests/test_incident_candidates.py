import pytest


VALID_CITIZEN_ID = "2200223333111"
OTHER_CITIZEN_ID = "2200223333112"


@pytest.fixture()
def citizen_token(app_client):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


@pytest.fixture()
def another_citizen_token(app_client):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": OTHER_CITIZEN_ID},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def _create_submission(app_client, token, title, description, incident_date="2026-09-20", location="Station X"):
    response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": title,
            "description": description,
            "incident_date": incident_date,
            "location": location,
        },
    )
    assert response.status_code == 201
    return response.get_json()["submission_id"]


def _create_assertion(app_client, token, submission_id, assertion_text):
    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {token}"},
        json={"assertion_text": assertion_text},
    )
    assert response.status_code == 201
    return response.get_json()["assertion_id"]


def _create_claim(app_client, token, submission_id, assertion_id):
    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}/claims",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.get_json()[0]


def test_incident_candidate_creation_is_provisional_and_traceable(app_client, citizen_token):
    submission_id = _create_submission(
        app_client,
        citizen_token,
        "Rear gate incident",
        "I saw Officer 12345 at the station gate after 21:00.",
    )
    assertion_id = _create_assertion(
        app_client,
        citizen_token,
        submission_id,
        "I saw Officer 12345 at the rear gate after 21:00.",
    )
    _create_claim(app_client, citizen_token, submission_id, assertion_id)

    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert "candidates" in payload
    assert payload["candidates"]
    candidate = payload["candidates"][0]
    assert candidate["status"] == "PROVISIONAL"
    assert candidate["provenance"] == "SYSTEM_DERIVED"
    assert candidate["source_submission_ids"]
    assert candidate["source_claim_ids"]
    assert "relationship" not in candidate.get("status", "").lower()


def test_possible_duplicate_relationship_is_explainable(app_client, citizen_token):
    first_submission = _create_submission(
        app_client,
        citizen_token,
        "Duplicate report A",
        "Officer 12345 was at the rear gate at 21:00 on 2026-09-20.",
    )
    second_submission = _create_submission(
        app_client,
        citizen_token,
        "Duplicate report B",
        "Officer 12345 was at the rear gate at 21:00 on 2026-09-20.",
    )
    first_assertion = _create_assertion(app_client, citizen_token, first_submission, "Officer 12345 was at the rear gate at 21:00.")
    second_assertion = _create_assertion(app_client, citizen_token, second_submission, "Officer 12345 was at the rear gate at 21:00.")
    _create_claim(app_client, citizen_token, first_submission, first_assertion)
    _create_claim(app_client, citizen_token, second_submission, second_assertion)

    response = app_client.post(
        f"/api/v1/citizen/submissions/{first_submission}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 201
    relationships = response.get_json()["relationships"]
    assert any(item["relationship_type"] == "POSSIBLE_DUPLICATE" for item in relationships)
    assert any("same" in str(item["explanation"]).lower() or "duplicate" in str(item["explanation"]).lower() for item in relationships)


def test_same_day_different_times_do_not_auto_merge(app_client, citizen_token):
    first_submission = _create_submission(
        app_client,
        citizen_token,
        "Incident at 09:00",
        "Officer 12345 was present at the station at 09:00.",
        incident_date="2026-09-20",
        location="Station X",
    )
    second_submission = _create_submission(
        app_client,
        citizen_token,
        "Incident at 18:00",
        "Officer 12345 was present at the station at 18:00.",
        incident_date="2026-09-20",
        location="Station X",
    )
    first_assertion = _create_assertion(app_client, citizen_token, first_submission, "Officer 12345 was present at the station at 09:00.")
    second_assertion = _create_assertion(app_client, citizen_token, second_submission, "Officer 12345 was present at the station at 18:00.")
    _create_claim(app_client, citizen_token, first_submission, first_assertion)
    _create_claim(app_client, citizen_token, second_submission, second_assertion)

    response = app_client.post(
        f"/api/v1/citizen/submissions/{first_submission}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 201
    relationships = response.get_json()["relationships"]
    assert all(item["relationship_type"] != "POSSIBLE_DUPLICATE" for item in relationships)


def test_cross_citizen_analysis_and_candidate_access_is_blocked(app_client, citizen_token, another_citizen_token):
    submission_id = _create_submission(
        app_client,
        citizen_token,
        "Other citizen incident",
        "Officer 12345 was seen at the station entrance.",
    )
    assertion_id = _create_assertion(app_client, citizen_token, submission_id, "Officer 12345 was seen at the station entrance.")
    _create_claim(app_client, citizen_token, submission_id, assertion_id)

    analysis = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/analyze",
        headers={"Authorization": f"Bearer {another_citizen_token}"},
    )
    assert analysis.status_code == 403

    listing = app_client.get(
        f"/api/v1/citizen/submissions/{submission_id}/incident-candidates",
        headers={"Authorization": f"Bearer {another_citizen_token}"},
    )
    assert listing.status_code == 403


def test_client_cannot_force_relationship_or_provenance(app_client, citizen_token):
    submission_id = _create_submission(
        app_client,
        citizen_token,
        "Dangerous payload",
        "Officer 12345 was seen at the station gate.",
    )
    assertion_id = _create_assertion(app_client, citizen_token, submission_id, "Officer 12345 was seen at the station gate.")
    _create_claim(app_client, citizen_token, submission_id, assertion_id)

    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"relationship_type": "CORROBORATES", "provenance": "VERIFIED_FACT"},
    )

    assert response.status_code in (200, 201, 400)
    if response.status_code == 200 or response.status_code == 201:
        payload = response.get_json()
        if isinstance(payload, dict):
            for item in payload.get("relationships", []):
                assert item.get("provenance") != "VERIFIED_FACT"


def test_submission_survives_candidate_failure_when_no_claims_exist(app_client, citizen_token):
    submission_id = _create_submission(
        app_client,
        citizen_token,
        "No claims yet",
        "I have not yet created any claim assertion.",
    )

    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 400
    assert "no claims" in response.get_json()["error"].lower()

    lookup = app_client.get(
        f"/api/v1/citizen/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert lookup.status_code == 200
    assert lookup.get_json()["submission_id"] == submission_id


def test_relationship_has_explanation_and_source_basis(app_client, citizen_token):
    submission_id = _create_submission(
        app_client,
        citizen_token,
        "Basis required",
        "Officer 12345 was at the station at 21:00.",
    )
    assertion_id = _create_assertion(app_client, citizen_token, submission_id, "Officer 12345 was at the station at 21:00.")
    _create_claim(app_client, citizen_token, submission_id, assertion_id)

    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["relationships"]
    for item in payload["relationships"]:
        assert item["explanation"]
        assert item["source_basis"]


def test_case_creation_gate_requires_review_before_case_generation(app_client, citizen_token):
    submission_id = _create_submission(
        app_client,
        citizen_token,
        "Candidate gate review",
        "I saw Officer 12345 outside the station gate at 21:00.",
    )
    assertion_id = _create_assertion(app_client, citizen_token, submission_id, "I saw Officer 12345 outside the station gate at 21:00.")
    _create_claim(app_client, citizen_token, submission_id, assertion_id)

    analysis = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert analysis.status_code == 201
    candidate = analysis.get_json()["candidates"][0]

    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/incident-candidates/{candidate['candidate_id']}/create-case",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code in {200, 202, 409}
    payload = response.get_json()
    assert payload["status"] in {"ALLOWED", "BLOCKED", "REVIEW_REQUIRED"}
    assert payload["candidate_id"] == candidate["candidate_id"]
    assert payload["gate"] == "case_creation"
    if payload["status"] == "ALLOWED":
        assert payload["case_reference"]


def test_new_incident_candidate_is_allowed_to_create_a_case_when_not_duplicative(app_client, citizen_token):
    submission_id = _create_submission(
        app_client,
        citizen_token,
        "New road obstruction",
        "An unmarked vehicle blocked the public footpath and refused to move near the civic center.",
        incident_date="2026-09-20",
        location="Civic Center",
    )
    assertion_id = _create_assertion(
        app_client,
        citizen_token,
        submission_id,
        "An unmarked vehicle blocked the public footpath near the civic center at 14:30.",
    )
    _create_claim(app_client, citizen_token, submission_id, assertion_id)

    analysis = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert analysis.status_code == 201
    candidate = analysis.get_json()["candidates"][0]
    assert candidate["status"] == "PROVISIONAL"
    assert analysis.get_json()["relationship_summary"]["duplicate_count"] == 0

    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/incident-candidates/{candidate['candidate_id']}/create-case",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ALLOWED"
    assert payload["case_reference"]
    assert payload["gate"] == "case_creation"


def test_same_actor_same_date_different_time_and_different_conduct_is_not_a_duplicate(app_client, citizen_token):
    first_submission = _create_submission(
        app_client,
        citizen_token,
        "First event",
        "Officer 12345 was at the station entrance at 09:00 and was courteous.",
        incident_date="2026-09-20",
        location="Station Entrance",
    )
    second_submission = _create_submission(
        app_client,
        citizen_token,
        "Second event",
        "Officer 12345 was at the station entrance at 18:00 and refused to identify themselves.",
        incident_date="2026-09-20",
        location="Station Entrance",
    )
    first_assertion = _create_assertion(app_client, citizen_token, first_submission, "Officer 12345 was at the station entrance at 09:00 and was courteous.")
    second_assertion = _create_assertion(app_client, citizen_token, second_submission, "Officer 12345 was at the station entrance at 18:00 and refused to identify themselves.")
    _create_claim(app_client, citizen_token, first_submission, first_assertion)
    _create_claim(app_client, citizen_token, second_submission, second_assertion)

    response = app_client.post(
        f"/api/v1/citizen/submissions/{first_submission}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 201
    relationships = response.get_json()["relationships"]
    assert not any(item["relationship_type"] == "POSSIBLE_DUPLICATE" for item in relationships)
    assert any(item["relationship_type"] in {"DISTINCT_FROM", "POTENTIALLY_RELATED"} for item in relationships)
