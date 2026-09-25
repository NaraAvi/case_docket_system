import pytest

from app.auth.service import TestIdentityRegistry

VALID_TEST_IDS = [
    "2200223333111",
    "2200223333112",
    "2200223333113",
]

STATION_COMMANDER_TEST_ID = "2200223333116"


def _login(client, test_id):
    return client.post("/api/v1/auth/login", json={"test_id": test_id})


def test_test_registry_contains_expected_synthetic_identities():
    registry = TestIdentityRegistry()
    identities = registry.list_identities()

    assert len(identities) == 7
    assert {item["role"] for item in identities} == {"citizen", "constable", "detective", "station_commander", "ipid"}
    assert sum(item["role"] == "citizen" for item in identities) == 3
    assert sum(item["role"] == "constable" for item in identities) == 1
    assert sum(item["role"] == "detective" for item in identities) == 1
    assert sum(item["role"] == "station_commander" for item in identities) == 1
    assert sum(item["role"] == "ipid" for item in identities) == 1
    assert all(item["active"] is True for item in identities)


@pytest.mark.parametrize("valid_test_id", VALID_TEST_IDS)
def test_valid_test_id_authenticates_successfully(app_client, valid_test_id):
    response = _login(app_client, valid_test_id)

    assert response.status_code == 200
    data = response.get_json()
    assert "access_token" in data
    assert data["role"] == "citizen"
    assert data["test_id"] == valid_test_id


def test_unknown_test_id_fails_authentication(app_client):
    response = _login(app_client, "2200223333119")

    assert response.status_code == 401
    assert response.get_json()["error"] == "Invalid or unknown test identity."


def test_malformed_test_id_fails_validation(app_client):
    response = _login(app_client, "bad-id")

    assert response.status_code == 400
    assert response.get_json()["error"] == "Test ID must be a 13-digit number."


def test_unauthenticated_request_to_protected_citizen_endpoint_fails(app_client):
    response = app_client.get("/api/v1/citizen/me")

    assert response.status_code == 401


def test_authenticated_citizen_can_access_profile(app_client):
    login_response = _login(app_client, VALID_TEST_IDS[0])
    token = login_response.get_json()["access_token"]

    response = app_client.get(
        "/api/v1/citizen/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["test_id"] == VALID_TEST_IDS[0]
    assert payload["role"] == "citizen"
    assert payload["active"] is True


def test_authenticated_citizen_receives_only_own_identity_information(app_client):
    login_response = _login(app_client, VALID_TEST_IDS[1])
    token = login_response.get_json()["access_token"]

    response = app_client.get(
        "/api/v1/citizen/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    payload = response.get_json()
    assert set(payload.keys()) == {"test_id", "full_name", "role", "active"}
    assert payload["test_id"] == VALID_TEST_IDS[1]
    assert payload["full_name"] == "Demo Citizen Two"


def test_citizen_role_is_established_correctly(app_client):
    login_response = _login(app_client, VALID_TEST_IDS[2])

    assert login_response.status_code == 200
    payload = login_response.get_json()
    assert payload["role"] == "citizen"
    assert payload["full_name"] == "Demo Citizen Three"


def test_station_commander_identity_authenticates_successfully(app_client):
    response = _login(app_client, STATION_COMMANDER_TEST_ID)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["role"] == "station_commander"
    assert payload["test_id"] == STATION_COMMANDER_TEST_ID
    assert payload["full_name"] == "Demo Station Commander One"


def test_station_commander_profile_is_available_to_authenticated_station_commander(app_client):
    login_response = _login(app_client, STATION_COMMANDER_TEST_ID)
    token = login_response.get_json()["access_token"]

    response = app_client.get(
        "/api/v1/station-commander/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["test_id"] == STATION_COMMANDER_TEST_ID
    assert payload["role"] == "station_commander"
    assert payload["active"] is True
    assert set(payload.keys()) == {"test_id", "full_name", "role", "active"}


def test_citizen_cannot_access_station_commander_profile(app_client):
    citizen_token = _login(app_client, VALID_TEST_IDS[0]).get_json()["access_token"]

    response = app_client.get(
        "/api/v1/station-commander/me",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 403


def test_constable_cannot_access_station_commander_profile(app_client):
    constable_token = _login(app_client, "2200223333114").get_json()["access_token"]

    response = app_client.get(
        "/api/v1/station-commander/me",
        headers={"Authorization": f"Bearer {constable_token}"},
    )

    assert response.status_code == 403


def test_detective_cannot_access_station_commander_profile(app_client):
    detective_token = _login(app_client, "2200223333115").get_json()["access_token"]

    response = app_client.get(
        "/api/v1/station-commander/me",
        headers={"Authorization": f"Bearer {detective_token}"},
    )

    assert response.status_code == 403


def test_station_commander_can_view_operational_docket_overview(app_client):
    citizen_token = _login(app_client, VALID_TEST_IDS[0]).get_json()["access_token"]
    station_token = _login(app_client, STATION_COMMANDER_TEST_ID).get_json()["access_token"]

    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_TEST_IDS[0], "Station Commander oversight case", "The commander should be able to review this docket without mutating it.")
    case_reference = case["case_reference"]

    response = app_client.get(
        "/api/v1/station-commander/dockets",
        headers={"Authorization": f"Bearer {station_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert any(item["case_reference"] == case_reference for item in payload)
    assert all("storage_reference" not in item for item in payload)


def test_station_commander_can_inspect_specific_docket(app_client):
    citizen_token = _login(app_client, VALID_TEST_IDS[1]).get_json()["access_token"]
    station_token = _login(app_client, STATION_COMMANDER_TEST_ID).get_json()["access_token"]

    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_TEST_IDS[1], "Specific docket inspection", "Commander should see basic operational summary and timeline.")
    case_reference = case["case_reference"]

    response = app_client.get(
        f"/api/v1/station-commander/dockets/{case_reference}",
        headers={"Authorization": f"Bearer {station_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["case_reference"] == case_reference
    assert payload["title"] == "Specific docket inspection"
    assert "timeline" in payload
    assert "status" in payload


def test_station_commander_audit_endpoint_is_read_only(app_client):
    citizen_token = _login(app_client, VALID_TEST_IDS[0]).get_json()["access_token"]
    station_token = _login(app_client, STATION_COMMANDER_TEST_ID).get_json()["access_token"]

    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_TEST_IDS[0], "Audit review case", "Audit endpoint should expose existing case actions without mutation.")
    case_reference = case["case_reference"]

    audit_response = app_client.get(
        f"/api/v1/station-commander/dockets/{case_reference}/audit",
        headers={"Authorization": f"Bearer {station_token}"},
    )

    assert audit_response.status_code == 200
    payload = audit_response.get_json()
    assert isinstance(payload, list)
    assert all("timestamp" in entry for entry in payload)
    assert all("action" in entry for entry in payload)
