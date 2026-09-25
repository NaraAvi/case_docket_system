import os
from datetime import UTC, datetime, timedelta

import pytest

from app import create_app
from app.scheduler import shutdown_sla_scheduler, start_sla_scheduler

CITIZEN_ID = "2200223333111"
CONSTABLE_ID = "2200223333114"
STATION_COMMANDER_ID = "2200223333116"


def _create_registered_case(app):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(CITIZEN_ID, {"title": "SLA scheduler case", "description": "Case used for scheduler tests."})
    case["status"] = "REGISTERED"
    case_service.update_case(case)
    return case


def _overdue_assignment(app, case_reference, hours=73):
    assignment_service = app.extensions["assignment_service"]
    return assignment_service.repository.create(
        {
            "assignment_id": f"ASG-SLA-{hours}",
            "case_reference": case_reference,
            "officer_id": CONSTABLE_ID,
            "officer_role": "constable",
            "assigned_by": STATION_COMMANDER_ID,
            "assigned_by_role": "station_commander",
            "assigned_at": (datetime.now(UTC) - timedelta(hours=hours)).isoformat(),
            "status": "ACTIVE",
        }
    )


def test_scheduler_invokes_existing_sla_evaluator(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app = create_app(testing=True)
    shutdown_sla_scheduler(app)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=73)

    calls = {"count": 0}
    original = app.extensions["automation_service"].list_breaches

    def wrapped():
        calls["count"] += 1
        return original()

    monkeypatch.setattr(app.extensions["automation_service"], "list_breaches", wrapped)
    scheduler = start_sla_scheduler(app, interval_seconds=1)
    scheduler.run_once()

    assert calls["count"] == 1
    escalations = app.extensions["escalation_service"].list_for_case(case["case_reference"])
    assert any(item.get("category") == "SLA_BREACH" for item in escalations)
    shutdown_sla_scheduler(app)


def test_scheduler_breaches_overdue_docket_without_a_request(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app = create_app(testing=True)
    shutdown_sla_scheduler(app)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=73)

    scheduler = start_sla_scheduler(app, interval_seconds=1)
    scheduler.run_once()

    escalations = app.extensions["escalation_service"].list_for_case(case["case_reference"])
    assert any(item.get("category") == "SLA_BREACH" for item in escalations)
    assert app.extensions["freeze_service"].get_current_freeze(case["case_reference"]) is not None
    shutdown_sla_scheduler(app)


def test_scheduler_keeps_non_overdue_docket_unchanged(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app = create_app(testing=True)
    shutdown_sla_scheduler(app)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=12)

    scheduler = start_sla_scheduler(app, interval_seconds=1)
    scheduler.run_once()

    escalations = app.extensions["escalation_service"].list_for_case(case["case_reference"])
    assert not any(item.get("category") == "SLA_BREACH" for item in escalations)
    assert app.extensions["freeze_service"].get_current_freeze(case["case_reference"]) is None
    shutdown_sla_scheduler(app)


def test_repeated_scheduler_runs_are_idempotent(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app = create_app(testing=True)
    shutdown_sla_scheduler(app)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=73)

    scheduler = start_sla_scheduler(app, interval_seconds=1)
    scheduler.run_once()
    scheduler.run_once()

    escalations = app.extensions["escalation_service"].list_for_case(case["case_reference"])
    sla_escalations = [item for item in escalations if item.get("category") == "SLA_BREACH"]
    assert len(sla_escalations) == 1
    assert len(app.extensions["freeze_service"].get_freeze_history(case["case_reference"])) == 1
    shutdown_sla_scheduler(app)


def test_scheduler_does_not_create_duplicate_sla_escalations(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app = create_app(testing=True)
    shutdown_sla_scheduler(app)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=73)

    scheduler = start_sla_scheduler(app, interval_seconds=1)
    scheduler.run_once()
    scheduler.run_once()

    escalations = app.extensions["escalation_service"].list_for_case(case["case_reference"])
    assert sum(1 for item in escalations if item.get("category") == "SLA_BREACH") == 1
    shutdown_sla_scheduler(app)


def test_scheduler_freeze_remains_correctly_applied(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app = create_app(testing=True)
    shutdown_sla_scheduler(app)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=74)

    scheduler = start_sla_scheduler(app, interval_seconds=1)
    scheduler.run_once()

    freeze = app.extensions["freeze_service"].get_current_freeze(case["case_reference"])
    assert freeze is not None
    assert freeze["status"] == "ACTIVE"
    assert "SLA_BREACH" in freeze["reason"]
    shutdown_sla_scheduler(app)


def test_scheduler_respects_existing_statutory_and_ipid_state(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app = create_app(testing=True)
    shutdown_sla_scheduler(app)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=73)

    freeze_service = app.extensions["freeze_service"]
    existing_freeze = freeze_service.freeze_case(
        case["case_reference"],
        STATION_COMMANDER_ID,
        "station_commander",
        reason="Already frozen for valid administrative review.",
    )
    existing_sla = app.extensions["escalation_service"].create_escalation(
        case["case_reference"],
        "system",
        "system_automation",
        "SLA_BREACH",
        "Existing SLA breach must remain the only active SLA breach.",
    )

    scheduler = start_sla_scheduler(app, interval_seconds=1)
    scheduler.run_once()

    current_freeze = freeze_service.get_current_freeze(case["case_reference"])
    current_sla_escalations = [item for item in app.extensions["escalation_service"].list_for_case(case["case_reference"]) if item.get("category") == "SLA_BREACH"]
    assert current_freeze["freeze_id"] == existing_freeze["freeze_id"]
    assert len(current_sla_escalations) == 1
    assert current_sla_escalations[0]["escalation_id"] == existing_sla["escalation_id"]
    shutdown_sla_scheduler(app)


def test_scheduler_startup_does_not_create_duplicate_workers_under_reloader(monkeypatch):
    app = create_app(testing=True)
    app.debug = True
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "false")
    first = start_sla_scheduler(app, interval_seconds=1)
    assert first is None
    second = start_sla_scheduler(app, interval_seconds=1)
    assert second is None

    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    third = start_sla_scheduler(app, interval_seconds=1)
    assert third is not None
    fourth = start_sla_scheduler(app, interval_seconds=1)
    assert fourth is third
    shutdown_sla_scheduler(app)


def test_scheduler_failure_does_not_break_request_handling(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app = create_app(testing=True)
    shutdown_sla_scheduler(app)
    scheduler = start_sla_scheduler(app, interval_seconds=1)

    def boom():
        raise RuntimeError("scheduler failure")

    monkeypatch.setattr(app.extensions["automation_service"], "trigger_registered_jobs", boom)
    scheduler.run_once()

    client = app.test_client()
    response = client.post("/api/v1/auth/login", json={"test_id": STATION_COMMANDER_ID})
    assert response.status_code == 200
    shutdown_sla_scheduler(app)
