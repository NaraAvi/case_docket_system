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


@pytest.fixture()
def submission_id(app_client, citizen_token):
    response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Broken security gate",
            "description": "The rear gate was left open overnight and the lock appears damaged.",
            "incident_date": "2026-09-10",
            "location": "Rear Gate",
        },
    )
    assert response.status_code == 201
    return response.get_json()["submission_id"]


def test_citizen_can_create_assertion_for_own_submission(app_client, citizen_token, submission_id):
    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "I saw Officer 12345 enter the rear gate after 22:00."},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["submission_id"] == submission_id
    assert payload["provenance"] == "CITIZEN_ASSERTED"
    assert payload["assertion_text"] == "I saw Officer 12345 enter the rear gate after 22:00."
    assert payload["source_actor_id"] == VALID_CITIZEN_ID


def test_citizen_cannot_create_assertion_for_another_citizens_submission(app_client, citizen_token, another_citizen_token, submission_id):
    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {another_citizen_token}"},
        json={"assertion_text": "This should never be accepted."},
    )

    assert response.status_code == 403


def test_client_cannot_force_assertion_provenance_or_verified_status(app_client, citizen_token, submission_id):
    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "assertion_text": "Officer 12345 assaulted me.",
            "provenance": "SYSTEM_OBSERVED",
            "verified": True,
            "status": "VERIFIED",
        },
    )

    assert response.status_code == 400
    assert "provenance" in response.get_json()["error"].lower() or "verified" in response.get_json()["error"].lower()


def test_submission_can_contain_multiple_assertions(app_client, citizen_token, submission_id):
    first = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "I saw Officer 12345 at the rear gate."},
    )
    second = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "The lock was broken after 22:00."},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    listed = app_client.get(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert listed.status_code == 200
    payload = listed.get_json()
    assert len(payload) >= 2
    assert {item["assertion_text"] for item in payload} >= {"I saw Officer 12345 at the rear gate.", "The lock was broken after 22:00."}


def test_assertion_content_cannot_be_overwritten_and_history_cannot_be_deleted(app_client, citizen_token, submission_id):
    created = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "I saw a yellow vehicle near the gate."},
    )
    assertion_id = created.get_json()["assertion_id"]

    update_response = app_client.put(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "I saw a blue vehicle near the gate."},
    )
    assert update_response.status_code in (400, 405)

    delete_response = app_client.delete(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert delete_response.status_code in (400, 405)

    get_response = app_client.get(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert get_response.status_code == 200
    assert get_response.get_json()["assertion_text"] == "I saw a yellow vehicle near the gate."


def test_assertion_can_generate_claims_without_verifying_them(app_client, citizen_token, submission_id):
    assertion = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "I saw Officer 12345 at the rear gate at 22:15."},
    )
    assertion_id = assertion.get_json()["assertion_id"]

    claims_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}/claims",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert claims_response.status_code == 201
    payload = claims_response.get_json()
    assert isinstance(payload, list)
    assert payload
    assert all(item["provenance"] == "CITIZEN_ASSERTED" for item in payload)
    assert all(item["source_assertion_ids"] for item in payload)
    assert all("verified" not in item for item in payload)


def test_claim_cannot_be_created_for_another_citizens_submission(app_client, citizen_token, another_citizen_token, submission_id):
    assertion = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "The lock was damaged at the station."},
    )
    assertion_id = assertion.get_json()["assertion_id"]

    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}/claims",
        headers={"Authorization": f"Bearer {another_citizen_token}"},
    )

    assert response.status_code == 403


def test_claim_payload_cannot_force_verification_or_system_provenance(app_client, citizen_token, submission_id):
    assertion = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "Officer 12345 was seen at the station."},
    )
    assertion_id = assertion.get_json()["assertion_id"]

    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}/claims",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"provenance": "SYSTEM_OBSERVED", "verified": True, "status": "VERIFIED"},
    )

    assert response.status_code == 400
    assert "provenance" in response.get_json()["error"].lower() or "verified" in response.get_json()["error"].lower()


def test_assertion_and_claim_creation_do_not_create_case_or_assignment(app_client, citizen_token):
    case_service = app_client.application.extensions["case_service"]
    initial_cases = len(case_service.get_all_cases())

    submission = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"title": "Broken gate", "description": "The rear gate was left unlocked overnight."},
    )
    submission_id = submission.get_json()["submission_id"]
    assertion = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "I saw Officer 12345 near the rear gate."},
    )
    assertion_id = assertion.get_json()["assertion_id"]
    app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}/claims",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert len(case_service.get_all_cases()) == initial_cases
    assert "assignment" not in app_client.application.extensions
