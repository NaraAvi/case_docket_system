import pytest

VALID_CITIZEN_ID = "2200223333111"
SECOND_CITIZEN_ID = "2200223333112"


@pytest.fixture()
def citizen_token(app_client):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def test_legacy_citizen_docket_creation_is_rejected_and_does_not_create_case(app_client, citizen_token):
    case_service = app_client.application.extensions["case_service"]
    initial_count = len(case_service.get_all_cases())

    response = app_client.post(
        "/api/v1/citizen/dockets",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Legacy bypass attempt",
            "description": "This direct citizen case creation path must be rejected.",
            "incident_date": "2026-09-10",
            "location": "Public Square",
        },
    )

    assert response.status_code == 410
    error = response.get_json().get("error", "")
    assert "submission" in error.lower() or "legacy" in error.lower()
    assert len(case_service.get_all_cases()) == initial_count


def test_protected_submission_is_created_with_received_status(app_client, citizen_token):
    response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Broken gate at school entrance",
            "description": "The gate has been left open and unsecured after hours.",
            "incident_date": "2026-09-10",
            "location": "School Entrance",
            "citizen_id": SECOND_CITIZEN_ID,
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["citizen_id"] == VALID_CITIZEN_ID
    assert payload["citizen_id"] != SECOND_CITIZEN_ID
    assert payload["status"] == "RECEIVED"
    assert "submission_id" in payload
    assert payload["receipt_timestamp"]
    assert "case_reference" not in payload or payload.get("case_reference") is None
    assert payload["original_content"]["title"] == "Broken gate at school entrance"
    assert payload["provenance"]["actor_id"] == VALID_CITIZEN_ID
    assert payload["provenance"]["actor_role"] == "citizen"


def test_submission_history_is_append_only_and_preserves_original_content(app_client, citizen_token):
    create_response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Flooded walkway",
            "description": "Rainwater is pooling and makes the path unsafe for pedestrians.",
        },
    )

    submission_id = create_response.get_json()["submission_id"]
    history_response = app_client.get(
        f"/api/v1/citizen/submissions/{submission_id}/history",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert history_response.status_code == 200
    history = history_response.get_json()
    assert len(history) >= 1
    assert history[0]["event_type"] == "submission_created"

    mutate_response = app_client.put(
        f"/api/v1/citizen/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"description": "The original content has been changed illegally."},
    )

    assert mutate_response.status_code == 400
    assert "immutable" in mutate_response.get_json()["error"].lower()

    get_response = app_client.get(
        f"/api/v1/citizen/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert get_response.status_code == 200
    assert get_response.get_json()["original_content"]["description"] == "Rainwater is pooling and makes the path unsafe for pedestrians."


def test_citizen_can_list_own_submissions_only(app_client, citizen_token):
    app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Broken streetlight",
            "description": "The streetlight near the bus stop is not working after dark.",
        },
    )

    response = app_client.get(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)
    assert payload and all(item["citizen_id"] == VALID_CITIZEN_ID for item in payload)
