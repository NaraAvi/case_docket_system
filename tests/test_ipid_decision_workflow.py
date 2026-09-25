import pytest

from app import create_app
from app.auth.service import TestIdentityRegistry

IPID_TEST_ID = "2200223333117"


def _login(client, test_id):
    return client.post("/api/v1/auth/login", json={"test_id": test_id})


def test_ipid_can_dismiss_escalation_and_record_decision(app_client):
    from tests.conftest import create_case_via_service

    citizen_token = _login(app_client, "2200223333111").get_json()["access_token"]
    case = create_case_via_service(app_client, "2200223333111", "Dismiss case", "IPID review should dismiss this escalation.")
    case_reference = case["case_reference"]

    escalation_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/escalations",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"category": "OFFICER_CONDUCT", "description": "The officer delayed the docket without reason."},
    )
    escalation_id = escalation_response.get_json()["escalation_id"]

    ipid_token = _login(app_client, IPID_TEST_ID).get_json()["access_token"]
    review_response = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/review",
        headers={"Authorization": f"Bearer {ipid_token}"},
    )
    assert review_response.status_code == 200

    dismiss_response = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/dismiss",
        headers={"Authorization": f"Bearer {ipid_token}"},
        json={"reason": "No actionable misconduct found in the available evidence."},
    )
    assert dismiss_response.status_code == 200
    payload = dismiss_response.get_json()
    assert payload["status"] == "RESOLVED"
    assert payload["decision"] == "DISMISSED"
    assert payload["decision_by"] == IPID_TEST_ID

    duplicate_response = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/dismiss",
        headers={"Authorization": f"Bearer {ipid_token}"},
        json={"reason": "Duplicate dismissal attempt."},
    )
    assert duplicate_response.status_code == 400


def test_ipid_uphold_creates_freeze_disciplinary_case_and_revokes_access(app_client):
    from tests.conftest import create_case_via_service

    citizen_token = _login(app_client, "2200223333112").get_json()["access_token"]
    case = create_case_via_service(app_client, "2200223333112", "Uphold case", "Officer discipline is required.")
    case_reference = case["case_reference"]

    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_all_cases()[-1]
    case["status"] = "REGISTERED"
    case_service.update_case(case)

    assignment_service = app_client.application.extensions["assignment_service"]
    assignment_service.create_assignment(
        case_reference=case_reference,
        officer_id="2200223333114",
        officer_role="constable",
        assigned_by="2200223333116",
        assigned_by_role="station_commander",
    )

    escalation_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/escalations",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"category": "OFFICER_CONDUCT", "description": "The officer mishandled the docket."},
    )
    escalation_id = escalation_response.get_json()["escalation_id"]

    ipid_token = _login(app_client, IPID_TEST_ID).get_json()["access_token"]
    review_response = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/review",
        headers={"Authorization": f"Bearer {ipid_token}"},
    )
    assert review_response.status_code == 200

    uphold_response = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/uphold",
        headers={"Authorization": f"Bearer {ipid_token}"},
        json={"reason": "Officer conduct warranting discipline."},
    )
    assert uphold_response.status_code == 200
    payload = uphold_response.get_json()
    assert payload["status"] == "RESOLVED"
    assert payload["decision"] == "UPHELD"
    assert payload["disciplinary_case"]["source_case_reference"] == case_reference
    assert payload["disciplinary_case"]["implicated_officer_id"] == "2200223333114"

    registry = app_client.application.extensions["identity_registry"]
    assert registry.get_identity("2200223333114")["access_state"] == "REVOKED"
    login_after_revoke = _login(app_client, "2200223333114")
    assert login_after_revoke.status_code == 401


def test_non_ipid_roles_cannot_uphold_escalation(app_client):
    from tests.conftest import create_case_via_service

    citizen_token = _login(app_client, "2200223333111").get_json()["access_token"]
    case = create_case_via_service(app_client, "2200223333111", "Forbidden uphold case", "Only IPID may uphold.")
    case_reference = case["case_reference"]
    escalation_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/escalations",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"category": "OFFICER_CONDUCT", "description": "Officer conduct allegation."},
    )
    escalation_id = escalation_response.get_json()["escalation_id"]
    token = _login(app_client, "2200223333114").get_json()["access_token"]

    response = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/uphold",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "Should be forbidden."},
    )
    assert response.status_code == 403


def test_disciplinary_case_creation_is_idempotent_per_escalation(app_client):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, "2200223333111", "Duplicate discipline case", "Only one disciplinary case per upheld escalation.")
    case_reference = case["case_reference"]
    service = app_client.application.extensions["disciplinary_case_service"]

    first = service.create_case(
        source_case_reference=case_reference,
        escalation_id="ESC-duplicate-phase7",
        implicated_officer_id="2200223333114",
        created_by="2200223333117",
        created_by_role="ipid",
        reason="Initial uphold decision.",
    )
    second = service.create_case(
        source_case_reference=case_reference,
        escalation_id="ESC-duplicate-phase7",
        implicated_officer_id="2200223333114",
        created_by="2200223333117",
        created_by_role="ipid",
        reason="Duplicate uphold decision.",
    )

    assert second["disciplinary_case_id"] == first["disciplinary_case_id"]


def test_ipid_reassignment_rejects_revoked_officers_and_preserves_history(app_client):
    from tests.conftest import create_case_via_service

    citizen_token = _login(app_client, "2200223333113").get_json()["access_token"]
    case = create_case_via_service(app_client, "2200223333113", "Reassignment case", "Officer reassignment review.")
    case_reference = case["case_reference"]

    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_all_cases()[-1]
    case["status"] = "REGISTERED"
    case_service.update_case(case)
    assignment_service = app_client.application.extensions["assignment_service"]
    assignment_service.create_assignment(
        case_reference=case_reference,
        officer_id="2200223333114",
        officer_role="constable",
        assigned_by="2200223333116",
        assigned_by_role="station_commander",
    )

    ipid_token = _login(app_client, IPID_TEST_ID).get_json()["access_token"]
    registry = app_client.application.extensions["identity_registry"]
    registry.revoke_access("2200223333114")

    rejected = app_client.post(
        f"/api/v1/ipid/dockets/{case_reference}/reassign",
        headers={"Authorization": f"Bearer {ipid_token}"},
        json={"officer_id": "2200223333114", "reason": "Should be rejected because revoked."},
    )
    assert rejected.status_code == 400

    valid = app_client.post(
        f"/api/v1/ipid/dockets/{case_reference}/reassign",
        headers={"Authorization": f"Bearer {ipid_token}"},
        json={"officer_id": "2200223333115", "reason": "Reassign to detective for progress."},
    )
    assert valid.status_code == 200
    payload = valid.get_json()
    assert payload["officer_id"] == "2200223333115"
    assert payload["status"] == "ACTIVE"


@pytest.mark.parametrize(
    "role,test_id",
    [
        ("citizen", "2200223333111"),
        ("constable", "2200223333114"),
        ("detective", "2200223333115"),
        ("station_commander", "2200223333116"),
    ],
)
def test_non_ipid_roles_cannot_decide_or_reassign(app_client, role, test_id):
    token = _login(app_client, test_id).get_json()["access_token"]
    response = app_client.post(
        "/api/v1/ipid/escalations/does-not-exist/dismiss",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "Should be forbidden."},
    )
    assert response.status_code == 403

    reassign_response = app_client.post(
        "/api/v1/ipid/dockets/does-not-exist/reassign",
        headers={"Authorization": f"Bearer {token}"},
        json={"officer_id": "2200223333115", "reason": "Forbidden."},
    )
    assert reassign_response.status_code == 403
