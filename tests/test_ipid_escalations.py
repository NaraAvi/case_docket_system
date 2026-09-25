import pytest


IPID_TEST_ID = "2200223333117"


def _login(client, test_id):
    return client.post("/api/v1/auth/login", json={"test_id": test_id})


def test_ipid_registry_and_authentication(app_client):
    response = _login(app_client, IPID_TEST_ID)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["role"] == "ipid"
    assert payload["test_id"] == IPID_TEST_ID

    registry = __import__("app.auth.service", fromlist=["TestIdentityRegistry"]).TestIdentityRegistry()
    identities = registry.list_identities()
    assert len(identities) == 7
    assert sum(item["role"] == "ipid" for item in identities) == 1


def test_citizen_can_create_and_list_own_escalation(app_client):
    from tests.conftest import create_case_via_service

    citizen_token = _login(app_client, "2200223333111").get_json()["access_token"]
    case = create_case_via_service(app_client, "2200223333111", "Escalation case", "Citizen needs to escalate this matter.")
    case_reference = case["case_reference"]

    escalation_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/escalations",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "category": "OFFICER_CONDUCT",
            "description": "The officer refused to register the docket properly.",
        },
    )
    assert escalation_response.status_code == 201
    payload = escalation_response.get_json()
    assert payload["case_reference"] == case_reference
    assert payload["status"] == "OPEN"
    assert payload["created_by"] == "2200223333111"
    assert payload["created_by_role"] == "citizen"
    assert payload["category"] == "OFFICER_CONDUCT"

    list_response = app_client.get(
        f"/api/v1/citizen/dockets/{case_reference}/escalations",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert list_response.status_code == 200
    items = list_response.get_json()
    assert len(items) == 1
    assert items[0]["case_reference"] == case_reference


def test_ipid_queue_and_review_workflow(app_client):
    from tests.conftest import create_case_via_service

    citizen_token = _login(app_client, "2200223333112").get_json()["access_token"]
    case = create_case_via_service(app_client, "2200223333112", "IPID queue case", "Escalation should be visible to IPID.")
    case_reference = case["case_reference"]

    create_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/escalations",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "category": "UNLAWFUL_DELAY",
            "description": "The docket has been delayed without a valid explanation.",
        },
    )
    assert create_response.status_code == 201
    escalation_id = create_response.get_json()["escalation_id"]

    ipid_token = _login(app_client, IPID_TEST_ID).get_json()["access_token"]
    queue_response = app_client.get(
        "/api/v1/ipid/escalations",
        headers={"Authorization": f"Bearer {ipid_token}"},
    )
    assert queue_response.status_code == 200
    queue = queue_response.get_json()
    assert any(item["escalation_id"] == escalation_id for item in queue)

    detail_response = app_client.get(
        f"/api/v1/ipid/escalations/{escalation_id}",
        headers={"Authorization": f"Bearer {ipid_token}"},
    )
    assert detail_response.status_code == 200
    detail = detail_response.get_json()
    assert detail["case_reference"] == case_reference
    assert detail["category"] == "UNLAWFUL_DELAY"

    review_response = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/review",
        headers={"Authorization": f"Bearer {ipid_token}"},
    )
    assert review_response.status_code == 200
    review_payload = review_response.get_json()
    assert review_payload["status"] == "UNDER_REVIEW"
    assert review_payload["reviewer_id"] == IPID_TEST_ID

    duplicate_review = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/review",
        headers={"Authorization": f"Bearer {ipid_token}"},
    )
    assert duplicate_review.status_code == 400


@pytest.mark.parametrize(
    "role,test_id",
    [
        ("citizen", "2200223333111"),
        ("constable", "2200223333114"),
        ("detective", "2200223333115"),
        ("station_commander", "2200223333116"),
    ],
)
def test_non_ipid_roles_cannot_access_ipid_endpoints(app_client, role, test_id):
    token = _login(app_client, test_id).get_json()["access_token"]

    response = app_client.get(
        "/api/v1/ipid/escalations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
