from datetime import UTC, datetime, timedelta

import pytest

from app import create_app

CITIZEN_ID = "2200223333111"
CONSTABLE_ID = "2200223333114"
DETECTIVE_ID = "2200223333115"
STATION_COMMANDER_ID = "2200223333116"


def _login(client, test_id):
    return client.post("/api/v1/auth/login", json={"test_id": test_id})


def _create_registered_case(app):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(CITIZEN_ID, {"title": "Operational oversight case", "description": "Case used for oversight tests."})
    case["status"] = "REGISTERED"
    case_service.update_case(case)
    return case


def test_station_commander_can_query_officer_audit_trail(app_client):
    app = create_app(testing=True)
    audit_service = app.extensions["audit_service"]
    case_reference = _create_registered_case(app)["case_reference"]
    audit_service.log(
        {
            "actor_id": CONSTABLE_ID,
            "actor_role": "constable",
            "action": "officer_case_reviewed",
            "case_reference": case_reference,
            "details": {"status": "REGISTERED"},
        }
    )

    station_token = _login(app_client, STATION_COMMANDER_ID).get_json()["access_token"]
    response = app_client.get(
        f"/api/v1/station-commander/officers/{CONSTABLE_ID}/audit",
        headers={"Authorization": f"Bearer {station_token}"},
    )

    assert response.status_code == 200
    assert any(event["actor_id"] == CONSTABLE_ID and event["action"] == "officer_case_reviewed" for event in response.get_json())


def test_station_commander_reviewed_officer_audit_event_is_logged(app_client):
    app = create_app(testing=True)
    audit_service = app.extensions["audit_service"]
    case_reference = _create_registered_case(app)["case_reference"]
    audit_service.log(
        {
            "actor_id": CONSTABLE_ID,
            "actor_role": "constable",
            "action": "officer_case_reviewed",
            "case_reference": case_reference,
            "details": {"status": "REGISTERED"},
        }
    )

    station_token = _login(app_client, STATION_COMMANDER_ID).get_json()["access_token"]
    app_client.get(
        f"/api/v1/station-commander/officers/{CONSTABLE_ID}/audit",
        headers={"Authorization": f"Bearer {station_token}"},
    )

    review_events = [event for event in audit_service.get_events_by_actor(STATION_COMMANDER_ID) if event["action"] == "station_commander_reviewed_officer_audit"]
    assert review_events
    assert review_events[0]["details"]["officer_id"] == CONSTABLE_ID


def test_non_station_commander_roles_cannot_view_officer_audit(app_client):
    for actor_id in [CITIZEN_ID, CONSTABLE_ID, DETECTIVE_ID]:
        token = _login(app_client, actor_id).get_json()["access_token"]
        response = app_client.get(
            f"/api/v1/station-commander/officers/{CONSTABLE_ID}/audit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


def test_sla_service_marks_breached_and_within_sla():
    app = create_app(testing=True)
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]

    case = _create_registered_case(app)
    started_at = (datetime.now(UTC) - timedelta(hours=73)).isoformat()
    assignment_service.repository.create(
        {
            "assignment_id": "ASG-999999",
            "case_reference": case["case_reference"],
            "officer_id": CONSTABLE_ID,
            "officer_role": "constable",
            "assigned_by": STATION_COMMANDER_ID,
            "assigned_by_role": "station_commander",
            "assigned_at": started_at,
            "status": "ACTIVE",
        }
    )
    breached = app.extensions["automation_service"].sla_service.calculate_case_sla(case["case_reference"])
    assert breached["status"] == "BREACHED"

    second_case = case_service.create_case(CITIZEN_ID, {"title": "Within SLA", "description": "This should not breach."})
    second_case["status"] = "REGISTERED"
    second_case["registered_at"] = (datetime.now(UTC) - timedelta(hours=12)).isoformat()
    case_service.update_case(second_case)
    within_sla = app.extensions["automation_service"].sla_service.calculate_case_sla(second_case["case_reference"])
    assert within_sla["status"] == "WITHIN_SLA"


def test_station_commander_sla_breaches_endpoint(app_client):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    assignment_service = app.extensions["assignment_service"]
    assignment_service.repository.create(
        {
            "assignment_id": "ASG-999998",
            "case_reference": case["case_reference"],
            "officer_id": CONSTABLE_ID,
            "officer_role": "constable",
            "assigned_by": STATION_COMMANDER_ID,
            "assigned_by_role": "station_commander",
            "assigned_at": (datetime.now(UTC) - timedelta(hours=73)).isoformat(),
            "status": "ACTIVE",
        }
    )

    token = _login(app_client, STATION_COMMANDER_ID).get_json()["access_token"]
    response = app_client.get("/api/v1/station-commander/sla/breaches", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert any(item["case_reference"] == case["case_reference"] for item in response.get_json())


def test_station_commander_can_upload_evidence_to_frozen_docket(app_client):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    freeze_service = app.extensions["freeze_service"]
    freeze_service.freeze_case(case["case_reference"], STATION_COMMANDER_ID, "station_commander", "Operational review")

    token = _login(app_client, STATION_COMMANDER_ID).get_json()["access_token"]
    response = app_client.post(
        f"/api/v1/station-commander/dockets/{case['case_reference']}/evidence",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "evidence_type": "PHOTO",
            "description": "Frozen docket image captured during oversight.",
            "filename": "oversight-photo.jpg",
            "storage_reference": "oversight-photo.jpg",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["case_reference"] == case["case_reference"]
    assert payload["submitted_by"] == STATION_COMMANDER_ID
    assert payload["evidence_type"] == "PHOTO"


def test_frozen_evidence_endpoint_rejects_unfrozen_docket(app_client):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    token = _login(app_client, STATION_COMMANDER_ID).get_json()["access_token"]
    response = app_client.post(
        f"/api/v1/station-commander/dockets/{case['case_reference']}/evidence",
        headers={"Authorization": f"Bearer {token}"},
        json={"evidence_type": "PHOTO", "description": "This should be rejected.", "filename": "rejected.jpg"},
    )

    assert response.status_code == 400
    assert "frozen" in response.get_json()["error"].lower()


def test_non_station_commander_roles_cannot_upload_frozen_evidence(app_client):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    app.extensions["freeze_service"].freeze_case(case["case_reference"], STATION_COMMANDER_ID, "station_commander", "review")

    for actor_id in [CITIZEN_ID, CONSTABLE_ID, DETECTIVE_ID]:
        token = _login(app_client, actor_id).get_json()["access_token"]
        response = app_client.post(
            f"/api/v1/station-commander/dockets/{case['case_reference']}/evidence",
            headers={"Authorization": f"Bearer {token}"},
            json={"evidence_type": "PHOTO", "description": "Blocked upload.", "filename": "blocked.jpg"},
        )
        assert response.status_code == 403
