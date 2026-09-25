import pytest

from app import create_app

VALID_CITIZEN_ID = "2200223333111"
VALID_CONSTABLE_ID = "2200223333114"
VALID_DETECTIVE_ID = "2200223333115"
VALID_STATION_COMMANDER_ID = "2200223333116"


def login(app_client, test_id):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": test_id},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def create_case_via_service(app_client, citizen_id, title, description, **kwargs):
    case_service = app_client.application.extensions["case_service"]
    case = case_service.create_case(citizen_id, {"title": title, "description": description, **kwargs})
    return case


def assign_detective_to_case(app_client, case_reference, detective_id=VALID_DETECTIVE_ID):
    station_commander_token = login(app_client, VALID_STATION_COMMANDER_ID)
    response = app_client.post(
        f"/api/v1/station-commander/dockets/{case_reference}/reassign",
        headers={"Authorization": f"Bearer {station_commander_token}"},
        json={"officer_id": detective_id, "reason": "Assigning detective for investigation."},
    )
    assert response.status_code == 200
    return response.get_json()


@pytest.fixture()
def app():
    return create_app(testing=True)


@pytest.fixture()
def app_client(app):
    with app.test_client() as client:
        yield client
