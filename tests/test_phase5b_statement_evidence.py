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
def other_citizen_token(app_client):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": OTHER_CITIZEN_ID},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def test_statement_records_server_generated_provenance_and_rejects_overwrite(app_client, citizen_token):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, "Fence incident", "Fence was cut open overnight.")
    response = app_client.post(
        f"/api/v1/citizen/dockets/{case['case_reference']}/statements",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"statement_text": "I saw the fence cut open at 22:15."},
    )
    assert response.status_code == 201
    statement = response.get_json()
    assert statement["provenance"]["actor_id"] == VALID_CITIZEN_ID
    assert statement["provenance"]["actor_role"] == "citizen"

    update_response = app_client.put(
        f"/api/v1/citizen/dockets/{case['case_reference']}/statements/{statement['statement_id']}",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"statement_text": "This statement must not replace the original."},
    )
    assert update_response.status_code == 400
    assert "immutable" in update_response.get_json()["error"].lower() or "append" in update_response.get_json()["error"].lower()

    fetch_response = app_client.get(
        f"/api/v1/citizen/dockets/{case['case_reference']}/statements",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert fetch_response.status_code == 200
    assert fetch_response.get_json()[0]["statement_text"] == "I saw the fence cut open at 22:15."


def test_evidence_rejects_client_controlled_case_binding_and_provenance(app_client, citizen_token, other_citizen_token):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, "Broken window", "Window broken overnight.")
    response = app_client.post(
        f"/api/v1/citizen/dockets/{case['case_reference']}/evidence",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "case_reference": "CD-9999-000001",
            "submitted_by": OTHER_CITIZEN_ID,
            "evidence_type": "PHOTO",
            "description": "This should be rejected.",
            "filename": "window.jpg",
            "sha256_hash": "bad-hash",
            "provenance": {"actor_id": OTHER_CITIZEN_ID, "actor_role": "citizen"},
        },
    )
    assert response.status_code == 400
    error = response.get_json()["error"].lower()
    assert "case" in error or "provenance" in error or "server" in error or "binding" in error

    evidence = app_client.post(
        f"/api/v1/citizen/dockets/{case['case_reference']}/evidence",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "evidence_type": "PHOTO",
            "description": "Own evidence is accepted.",
            "filename": "window.jpg",
        },
    )
    assert evidence.status_code == 201
    payload = evidence.get_json()
    assert payload["submitted_by"] == VALID_CITIZEN_ID
    assert payload["case_reference"] == case["case_reference"]
    assert payload["provenance"]["actor_id"] == VALID_CITIZEN_ID
    assert payload["provenance"]["actor_role"] == "citizen"
    assert payload["integrity_status"] in {"VERIFIED", "UNHASHED"}
    assert payload["content_hash"] == payload["sha256_hash"] or payload["sha256_hash"] is None
