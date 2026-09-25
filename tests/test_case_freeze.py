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
    case = case_service.create_case(CITIZEN_ID, {"title": "Freeze case", "description": "Case subject to freeze testing."})
    case["status"] = "REGISTERED"
    case_service.update_case(case)
    return case


def test_freeze_service_freezes_case_and_tracks_history(app):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    freeze_service = app.extensions["freeze_service"]

    freeze = freeze_service.freeze_case(
        case_reference=case["case_reference"],
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="Operational review pending.",
    )

    assert freeze["status"] == "ACTIVE"
    assert freeze_service.is_case_frozen(case["case_reference"]) is True
    assert freeze_service.get_current_freeze(case["case_reference"])["freeze_id"] == freeze["freeze_id"]

    history = freeze_service.get_freeze_history(case["case_reference"])
    assert [item["status"] for item in history] == ["ACTIVE"]
    assert any(entry["action"] == "case_frozen" for entry in app.extensions["audit_service"].get_for_case(case["case_reference"]))

    unfreeze = freeze_service.unfreeze_case(
        case_reference=case["case_reference"],
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="Review complete.",
    )
    assert unfreeze["status"] == "RELEASED"
    assert freeze_service.is_case_frozen(case["case_reference"]) is False
    assert freeze_service.get_current_freeze(case["case_reference"]) is None
    assert any(entry["action"] == "case_unfrozen" for entry in app.extensions["audit_service"].get_for_case(case["case_reference"]))


def test_second_freeze_creates_new_history_record(app):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    freeze_service = app.extensions["freeze_service"]

    first = freeze_service.freeze_case(case["case_reference"], STATION_COMMANDER_ID, "station_commander", "first freeze")
    freeze_service.unfreeze_case(case["case_reference"], STATION_COMMANDER_ID, "station_commander", "released")
    second = freeze_service.freeze_case(case["case_reference"], STATION_COMMANDER_ID, "station_commander", "second freeze")

    history = freeze_service.get_freeze_history(case["case_reference"])
    assert [item["freeze_id"] for item in history] == [first["freeze_id"], second["freeze_id"]]
    assert {item["freeze_id"]: item["status"] for item in history} == {
        first["freeze_id"]: "RELEASED",
        second["freeze_id"]: "ACTIVE",
    }


def test_constable_and_detective_mutations_are_blocked_while_frozen(app):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    constable_service = app.extensions["constable_registration_service"]
    investigation_service = app.extensions["investigation_service"]
    freeze_service = app.extensions["freeze_service"]
    assignment_service = app.extensions["assignment_service"]

    assignment_service.create_assignment(
        case_reference=case["case_reference"],
        officer_id=DETECTIVE_ID,
        officer_role="detective",
        assigned_by=STATION_COMMANDER_ID,
        assigned_by_role="station_commander",
    )

    freeze_service.freeze_case(case["case_reference"], STATION_COMMANDER_ID, "station_commander", "internal review")

    with pytest.raises(ValueError, match="frozen"):
        constable_service.create_flag(case["case_reference"], CONSTABLE_ID, {"category": "OTHER", "notes": "Blocked while frozen."})

    with pytest.raises(ValueError, match="frozen"):
        investigation_service.create_investigation(case["case_reference"], DETECTIVE_ID, {"notes": "Blocked while frozen."})


def test_station_commander_docket_response_exposes_freeze_metadata(app):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    freeze_service = app.extensions["freeze_service"]
    station_service = app.extensions["station_commander_service"]

    freeze_service.freeze_case(case["case_reference"], STATION_COMMANDER_ID, "station_commander", "review")

    docket = station_service.get_docket(case["case_reference"])
    assert docket["is_frozen"] is True
    assert docket["current_freeze"]["status"] == "ACTIVE"
    assert docket["current_freeze"]["case_reference"] == case["case_reference"]


def test_public_freeze_api_is_not_exposed(app_client):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, CITIZEN_ID, "Freeze API denials", "No public freeze API should exist.")
    case_reference = case["case_reference"]

    for actor_id in [CITIZEN_ID, CONSTABLE_ID, DETECTIVE_ID]:
        token = _login(app_client, actor_id).get_json()["access_token"]
        response = app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/freeze",
            headers={"Authorization": f"Bearer {token}"},
            json={"reason": "Attempted freeze."},
        )
        assert response.status_code == 404


def test_case_freeze_does_not_replace_assignment_history(app):
    app = create_app(testing=True)
    case = _create_registered_case(app)
    assignment_service = app.extensions["assignment_service"]
    freeze_service = app.extensions["freeze_service"]

    assignment = assignment_service.create_assignment(
        case_reference=case["case_reference"],
        officer_id=CONSTABLE_ID,
        officer_role="constable",
        assigned_by=STATION_COMMANDER_ID,
        assigned_by_role="station_commander",
    )
    freeze_service.freeze_case(case["case_reference"], STATION_COMMANDER_ID, "station_commander", "freeze during review")

    history = assignment_service.get_assignment_history_for_case(case["case_reference"])
    assert [item["assignment_id"] for item in history] == [assignment["assignment_id"]]
    assert history[0]["status"] == "ACTIVE"
    assert freeze_service.is_case_frozen(case["case_reference"]) is True
