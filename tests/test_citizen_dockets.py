import hashlib
import io

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


@pytest.fixture()
def second_citizen_token(app_client):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": SECOND_CITIZEN_ID},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def test_legacy_citizen_docket_creation_is_retired(app_client, citizen_token):
    response = app_client.post(
        "/api/v1/citizen/dockets",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Legacy bypass attempt",
            "description": "The direct docket path must be retired under the protected-submission contract.",
            "incident_date": "2026-09-10",
            "location": "Public Square",
        },
    )

    assert response.status_code == 410
    payload = response.get_json()
    assert "submission" in payload["error"].lower()

    case_service = app_client.application.extensions["case_service"]
    assert len(case_service.get_all_cases()) == 0


def test_authenticated_citizen_can_create_protected_submission(app_client, citizen_token):
    response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Broken gate at main entrance",
            "description": "The gate is damaged and needs inspection.",
            "incident_date": "2026-09-01",
            "location": "Main Entrance",
            "citizen_id": SECOND_CITIZEN_ID,
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["citizen_id"] == VALID_CITIZEN_ID
    assert payload["status"] == "RECEIVED"
    assert payload["submission_id"].startswith("SUB-")
    assert "case_reference" not in payload or payload.get("case_reference") is None
    assert payload["provenance"]["actor_id"] == VALID_CITIZEN_ID
    assert payload["receipt_timestamp"]

    case_service = app_client.application.extensions["case_service"]
    assert len(case_service.get_all_cases()) == 0


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
    assert history[0]["event_type"] == "submission_created"

    mutate_response = app_client.put(
        f"/api/v1/citizen/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"description": "This content should never mutate."},
    )
    assert mutate_response.status_code == 400

    get_response = app_client.get(
        f"/api/v1/citizen/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert get_response.status_code == 200
    assert get_response.get_json()["original_content"]["description"] == "Rainwater is pooling and makes the path unsafe for pedestrians."


def test_citizen_can_list_own_submissions_only(app_client, citizen_token, second_citizen_token):
    app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Broken streetlight",
            "description": "The streetlight near the bus stop is not working after dark.",
        },
    )
    app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {second_citizen_token}"},
        json={
            "title": "Another citizen incident",
            "description": "This belongs to the second citizen and must stay separate.",
        },
    )

    response = app_client.get(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)
    assert all(item["citizen_id"] == VALID_CITIZEN_ID for item in payload)


def test_submission_creation_has_server_generated_receipt_timestamp(app_client, citizen_token):
    response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Receipt timestamp test",
            "description": "The server should stamp the receipt and never trust the client clock.",
        },
    )

    payload = response.get_json()
    assert response.status_code == 201
    assert payload["receipt_timestamp"]
    assert payload["provenance"]["receipt_timestamp"] == payload["receipt_timestamp"]


def test_rule_and_control_evaluations_are_persisted_for_case_creation(app_client, citizen_token):
    create_response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Gate obstruction complaint",
            "description": "The officer blocked the gate and refused access at the station entrance.",
            "incident_date": "2026-09-10",
            "location": "Station Entrance",
        },
    )
    submission_id = create_response.get_json()["submission_id"]

    assertion_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "The officer blocked the gate and refused access at the station entrance."},
    )
    assert assertion_response.status_code == 201
    assertion_id = assertion_response.get_json()["assertion_id"]

    claim_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions/{assertion_id}/claims",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={},
    )
    assert claim_response.status_code == 201

    analyze_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/analyze",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={},
    )
    assert analyze_response.status_code == 201
    candidate_id = analyze_response.get_json()["candidate"]["candidate_id"]

    case_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/incident-candidates/{candidate_id}/create-case",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={},
    )
    assert case_response.status_code in {200, 202}

    rule_repo = app_client.application.extensions["rule_evaluation_repository"]
    control_repo = app_client.application.extensions["control_evaluation_repository"]
    assert rule_repo.list_all()
    assert control_repo.list_all()


def test_citizen_evidence_is_server_bound_and_preserved(app_client, citizen_token):
    create_response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Evidence integrity check",
            "description": "A citizen-submitted photo should be hashed and bound to the protected submission.",
        },
    )
    submission_id = create_response.get_json()["submission_id"]

    bad_payload = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/evidence",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "evidence_type": "PHOTO",
            "description": "Client-supplied evidence metadata must not override server provenance.",
            "sha256_hash": "deadbeef",
            "source_actor_id": "9999999999999",
        },
    )
    assert bad_payload.status_code == 400

    good_payload = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/evidence",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "evidence_type": "PHOTO",
            "description": "Front gate photo.",
            "filename": "gate.jpg",
            "content_type": "image/jpeg",
            "storage_reference": "evidence/gate.jpg",
        },
    )
    assert good_payload.status_code == 201
    payload = good_payload.get_json()
    assert payload["submission_id"] == submission_id
    assert payload["source_actor_id"] == "2200223333111"
    assert payload["integrity_status"] == "VERIFIED"
    assert payload["sha256_hash"]

    list_response = app_client.get(
        f"/api/v1/citizen/submissions/{submission_id}/evidence",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert list_response.status_code == 200
    assert len(list_response.get_json()) == 1


def test_citizen_correction_and_withdrawal_are_append_only(app_client, citizen_token):
    create_response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Correction and withdrawal check",
            "description": "The original statement must remain preserved while a correction is logged.",
        },
    )
    submission_id = create_response.get_json()["submission_id"]

    assertion_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/assertions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"assertion_text": "The event happened on Main Road."},
    )
    original_assertion_id = assertion_response.get_json()["assertion_id"]

    correction_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/corrections",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "assertion_id": original_assertion_id,
            "assertion_text": "I meant Main Street.",
            "reason": "Clarification after review.",
        },
    )
    assert correction_response.status_code == 201
    correction_payload = correction_response.get_json()
    assert correction_payload["relationship_type"] == "correction_for"
    assert correction_payload["original_assertion_id"] == original_assertion_id


def test_protected_submission_evidence_upload_uses_real_server_hash_and_media_endpoint(app_client, citizen_token):
    create_response = app_client.post(
        "/api/v1/citizen/submissions",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "Protected evidence upload",
            "description": "The citizen evidence must be server-bound and retrievable through the protected submission path.",
        },
    )
    submission_id = create_response.get_json()["submission_id"]

    content = b"real protected evidence bytes"
    response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/evidence",
        data={
            "file": (io.BytesIO(content), "gate.jpg"),
            "evidence_type": "PHOTO",
            "description": "Front gate photograph.",
        },
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["submission_id"] == submission_id
    assert payload["sha256_hash"] == hashlib.sha256(content).hexdigest()
    assert payload["storage_reference"].startswith("evidence/")

    stored_filename = payload["storage_reference"].split("/", 1)[1]
    media = app_client.get(
        f"/api/v1/media/evidence/{stored_filename}",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert media.status_code == 200
    assert media.data == content

    withdrawal_response = app_client.post(
        f"/api/v1/citizen/submissions/{submission_id}/withdrawal",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"reason": "Citizen withdrew the submission after review."},
    )
    assert withdrawal_response.status_code == 201
    withdrawal_payload = withdrawal_response.get_json()
    assert withdrawal_payload["submission_id"] == submission_id
    assert withdrawal_payload["status"] == "REQUESTED"

    get_submission = app_client.get(
        f"/api/v1/citizen/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert get_submission.status_code == 200
    assert get_submission.get_json()["description"] == create_response.get_json()["description"]
