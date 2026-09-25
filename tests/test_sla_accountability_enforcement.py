from datetime import UTC, datetime, timedelta

from app import create_app

CITIZEN_ID = "2200223333111"
CONSTABLE_ID = "2200223333114"
STATION_COMMANDER_ID = "2200223333116"


def _create_registered_case(app):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(CITIZEN_ID, {"title": "SLA enforcement case", "description": "Case used for SLA enforcement tests."})
    case["status"] = "REGISTERED"
    case_service.update_case(case)
    return case


def _overdue_assignment(app, case_reference, hours=73):
    assignment_service = app.extensions["assignment_service"]
    assignment = assignment_service.repository.create(
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
    return assignment


def test_request_triggers_automatic_sla_enforcement_for_overdue_cases(app_client):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=73)

    token = app_client.post("/api/v1/auth/login", json={"test_id": STATION_COMMANDER_ID}).get_json()["access_token"]
    response = app_client.get("/api/v1/station-commander/dockets", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    escalations = app.extensions["escalation_service"].list_for_case(case["case_reference"])
    assert any(item.get("category") == "SLA_BREACH" for item in escalations)
    assert app.extensions["freeze_service"].get_current_freeze(case["case_reference"]) is not None


def test_sla_breach_creates_exactly_one_sla_breach_escalation():
    app = create_app(testing=True)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=73)

    result = app.extensions["automation_service"].enforce_sla_breach(case["case_reference"])

    assert result["breached"] is True
    assert result["escalation"]["category"] == "SLA_BREACH"
    assert result["escalation"]["source"] == "MANUAL"
    assert result["freeze"]["status"] == "ACTIVE"

    escalations = app.extensions["escalation_service"].list_for_case(case["case_reference"])
    sla_escalations = [item for item in escalations if item.get("category") == "SLA_BREACH"]
    assert len(sla_escalations) == 1
    assert any(item["case_reference"] == case["case_reference"] for item in app.extensions["escalation_service"].list_queue())


def test_sla_breach_freezes_the_docket_and_is_visible_to_ipid_queue():
    app = create_app(testing=True)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=74)

    app.extensions["automation_service"].enforce_sla_breach(case["case_reference"])

    freeze = app.extensions["freeze_service"].get_current_freeze(case["case_reference"])
    assert freeze is not None
    assert freeze["status"] == "ACTIVE"
    assert freeze["reason"] is not None and "SLA_BREACH" in freeze["reason"]
    assert any(item["case_reference"] == case["case_reference"] for item in app.extensions["ipid_service"].list_queue())


def test_rerunning_sla_evaluation_does_not_duplicate_escalation_or_freeze():
    app = create_app(testing=True)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=73)

    first = app.extensions["automation_service"].enforce_sla_breach(case["case_reference"])
    second = app.extensions["automation_service"].enforce_sla_breach(case["case_reference"])

    assert first["escalation"]["escalation_id"] == second["escalation"]["escalation_id"]
    escalation_history = app.extensions["escalation_service"].list_for_case(case["case_reference"])
    assert len([item for item in escalation_history if item.get("category") == "SLA_BREACH"]) == 1
    assert len(app.extensions["freeze_service"].get_freeze_history(case["case_reference"])) == 1


def test_frozen_periods_do_not_count_toward_72_hour_sla_window():
    app = create_app(testing=True)
    case = _create_registered_case(app)
    case["submitted_at"] = (datetime.now(UTC) - timedelta(hours=40)).isoformat()
    case["registered_at"] = (datetime.now(UTC) - timedelta(hours=35)).isoformat()
    app.extensions["case_service"].update_case(case)

    freeze_service = app.extensions["freeze_service"]
    freeze_service.freeze_case(
        case["case_reference"],
        STATION_COMMANDER_ID,
        "station_commander",
        reason="Operational review",
    )

    freeze_service.repository.update(
        freeze_service.get_current_freeze(case["case_reference"]) ["freeze_id"],
        {
            **freeze_service.get_current_freeze(case["case_reference"]),
            "frozen_at": (datetime.now(UTC) - timedelta(hours=30)).isoformat(),
            "released_at": (datetime.now(UTC) - timedelta(hours=10)).isoformat(),
            "status": "RELEASED",
        },
    )

    assignment_service = app.extensions["assignment_service"]
    assignment_service.repository.create(
        {
            "assignment_id": "ASG-SLA-FROZEN",
            "case_reference": case["case_reference"],
            "officer_id": CONSTABLE_ID,
            "officer_role": "constable",
            "assigned_by": STATION_COMMANDER_ID,
            "assigned_by_role": "station_commander",
            "assigned_at": (datetime.now(UTC) - timedelta(hours=55)).isoformat(),
            "status": "ACTIVE",
        }
    )

    result = app.extensions["decision_engine"].evaluate_sla_compliance(case["case_reference"])
    assert result["breached"] is False


def test_existing_active_freeze_is_not_duplicated_for_sla_breach():
    app = create_app(testing=True)
    case = _create_registered_case(app)
    _overdue_assignment(app, case["case_reference"], hours=75)

    freeze_service = app.extensions["freeze_service"]
    existing_freeze = freeze_service.freeze_case(
        case["case_reference"],
        STATION_COMMANDER_ID,
        "station_commander",
        reason="Already frozen for another valid reason.",
    )

    result = app.extensions["automation_service"].enforce_sla_breach(case["case_reference"])

    assert result["freeze"]["freeze_id"] == existing_freeze["freeze_id"]
    assert len(freeze_service.get_freeze_history(case["case_reference"])) == 1


def test_statutory_referral_still_behaves_exactly_as_before():
    app = create_app(testing=True)
    case_service = app.extensions["case_service"]
    case = case_service.create_case(CITIZEN_ID, {"title": "Statutory referral case", "description": "Will trigger mandatory referral."})
    case["status"] = "REGISTERED"
    case_service.update_case(case)

    result = app.extensions["statutory_referral_service"].screen_docket_submission(case["case_reference"], CITIZEN_ID)

    assert result["referred"] is False
