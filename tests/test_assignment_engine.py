import pytest

from app import create_app

CITIZEN_ID = "2200223333111"
CONSTABLE_ID = "2200223333114"
DETECTIVE_ID = "2200223333115"
STATION_COMMANDER_ID = "2200223333116"


def _login(client, test_id):
    return client.post("/api/v1/auth/login", json={"test_id": test_id})


def _create_registered_docket_via_service():
    app = create_app(testing=True)
    case_service = app.extensions["case_service"]
    case = case_service.create_case(CITIZEN_ID, {"title": "Assignment case", "description": "Case for assignment tests."})
    case["status"] = "REGISTERED"
    case_service.update_case(case)
    return app, case


def test_assignment_service_can_create_and_fetch_current_assignment():
    app, case = _create_registered_docket_via_service()
    assignment_service = app.extensions["assignment_service"]

    assignment = assignment_service.create_assignment(
        case_reference=case["case_reference"],
        officer_id=CONSTABLE_ID,
        officer_role="constable",
        assigned_by=STATION_COMMANDER_ID,
        assigned_by_role="station_commander",
    )

    assert assignment["status"] == "ACTIVE"
    assert assignment["case_reference"] == case["case_reference"]
    assert assignment["officer_id"] == CONSTABLE_ID
    assert assignment["officer_role"] == "constable"

    current = assignment_service.get_current_assignment_for_case(case["case_reference"])
    assert current["assignment_id"] == assignment["assignment_id"]
    assert current["status"] == "ACTIVE"


def test_assignment_history_is_retained_across_reassignment():
    app, case = _create_registered_docket_via_service()
    assignment_service = app.extensions["assignment_service"]

    first = assignment_service.create_assignment(
        case_reference=case["case_reference"],
        officer_id=CONSTABLE_ID,
        officer_role="constable",
        assigned_by=STATION_COMMANDER_ID,
        assigned_by_role="station_commander",
    )
    second = assignment_service.create_replacement_assignment(
        case_reference=case["case_reference"],
        officer_id=DETECTIVE_ID,
        officer_role="detective",
        assigned_by=STATION_COMMANDER_ID,
        assigned_by_role="station_commander",
        previous_assignment_id=first["assignment_id"],
        reason="Operational review required.",
    )

    history = assignment_service.get_assignment_history_for_case(case["case_reference"])
    assert [item["assignment_id"] for item in history] == [first["assignment_id"], second["assignment_id"]]
    assert {item["assignment_id"]: item["status"] for item in history} == {
        first["assignment_id"]: "ENDED",
        second["assignment_id"]: "ACTIVE",
    }


def test_station_commander_can_force_reassign_docket(app_client):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, CITIZEN_ID, "Reassignment case", "The commander should be able to reassign this docket.")
    case_reference = case["case_reference"]

    case["status"] = "REGISTERED"
    app_client.application.extensions["case_service"].update_case(case)

    station_login = _login(app_client, STATION_COMMANDER_ID)
    station_token = station_login.get_json()["access_token"]

    response = app_client.post(
        f"/api/v1/station-commander/dockets/{case_reference}/reassign",
        headers={"Authorization": f"Bearer {station_token}"},
        json={"officer_id": CONSTABLE_ID, "reason": "Operational handoff."},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["case_reference"] == case_reference
    assert payload["status"] == "ACTIVE"
    assert payload["officer_id"] == CONSTABLE_ID
    assert payload["officer_role"] == "constable"
    assert payload["assigned_by"] == STATION_COMMANDER_ID
    assert payload["assigned_by_role"] == "station_commander"


def test_citizen_cannot_force_reassign_docket(app_client):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, CITIZEN_ID, "Citizen reassignment denial", "Citizen should not trigger a force reassignment.")
    case_reference = case["case_reference"]
    citizen_token = _login(app_client, CITIZEN_ID).get_json()["access_token"]

    response = app_client.post(
        f"/api/v1/station-commander/dockets/{case_reference}/reassign",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"officer_id": CONSTABLE_ID},
    )
    assert response.status_code == 403


def test_constable_cannot_force_reassign_docket(app_client):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, CITIZEN_ID, "Constable reassignment denial", "Constable should not perform reassignment.")
    case_reference = case["case_reference"]
    constable_token = _login(app_client, CONSTABLE_ID).get_json()["access_token"]

    response = app_client.post(
        f"/api/v1/station-commander/dockets/{case_reference}/reassign",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"officer_id": DETECTIVE_ID},
    )
    assert response.status_code == 403


def test_detective_cannot_force_reassign_docket(app_client):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, CITIZEN_ID, "Detective reassignment denial", "Detective should not perform reassignment.")
    case_reference = case["case_reference"]
    detective_token = _login(app_client, DETECTIVE_ID).get_json()["access_token"]

    response = app_client.post(
        f"/api/v1/station-commander/dockets/{case_reference}/reassign",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"officer_id": CONSTABLE_ID},
    )
    assert response.status_code == 403


def test_unauthenticated_user_cannot_force_reassign_docket(app_client):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, CITIZEN_ID, "Unauthenticated reassignment denial", "Unathenticated should be blocked.")
    case_reference = case["case_reference"]

    response = app_client.post(
        f"/api/v1/station-commander/dockets/{case_reference}/reassign",
        json={"officer_id": CONSTABLE_ID},
    )
    assert response.status_code == 401


def test_invalid_target_role_is_rejected():
    app, case = _create_registered_docket_via_service()
    assignment_service = app.extensions["assignment_service"]

    with pytest.raises(ValueError, match="eligible operational officer"):
        assignment_service.create_assignment(
            case_reference=case["case_reference"],
            officer_id=CITIZEN_ID,
            officer_role="citizen",
            assigned_by=STATION_COMMANDER_ID,
            assigned_by_role="station_commander",
        )


def test_same_officer_reassignment_is_rejected():
    app, case = _create_registered_docket_via_service()
    assignment_service = app.extensions["assignment_service"]
    assignment_service.create_assignment(
        case_reference=case["case_reference"],
        officer_id=CONSTABLE_ID,
        officer_role="constable",
        assigned_by=STATION_COMMANDER_ID,
        assigned_by_role="station_commander",
    )

    with pytest.raises(ValueError, match="already assigned"):
        assignment_service.create_assignment(
            case_reference=case["case_reference"],
            officer_id=CONSTABLE_ID,
            officer_role="constable",
            assigned_by=STATION_COMMANDER_ID,
            assigned_by_role="station_commander",
        )


def test_client_cannot_spoof_assignment_metadata():
    app, case = _create_registered_docket_via_service()
    assignment_service = app.extensions["assignment_service"]

    assignment = assignment_service.create_assignment(
        case_reference=case["case_reference"],
        officer_id=CONSTABLE_ID,
        officer_role="constable",
        assigned_by="2200223333111",
        assigned_by_role="citizen",
        override_authority=False,
    )

    assert assignment["assigned_by"] is None
    assert assignment["assigned_by_role"] is None


def test_detective_investigation_requires_active_case_assignment():
    app, case = _create_registered_docket_via_service()
    investigation_service = app.extensions["investigation_service"]

    with pytest.raises(ValueError, match="assigned|assignment"):
        investigation_service.create_investigation(case["case_reference"], DETECTIVE_ID, {"notes": "No detective assignment exists yet."})


def test_unknown_case_and_unknown_officer_are_rejected():
    app = create_app(testing=True)
    assignment_service = app.extensions["assignment_service"]

    with pytest.raises(ValueError, match="Case not found"):
        assignment_service.create_assignment(
            case_reference="CD-999999-000001",
            officer_id=CONSTABLE_ID,
            officer_role="constable",
            assigned_by=STATION_COMMANDER_ID,
            assigned_by_role="station_commander",
        )

    case = app.extensions["case_service"].create_case(CITIZEN_ID, {"title": "Unknown officer", "description": "This case exists but officer does not."})
    case["status"] = "REGISTERED"
    app.extensions["case_service"].update_case(case)

    with pytest.raises(ValueError, match="Target officer"):
        assignment_service.create_assignment(
            case_reference=case["case_reference"],
            officer_id="2200223333119",
            officer_role="constable",
            assigned_by=STATION_COMMANDER_ID,
            assigned_by_role="station_commander",
        )
