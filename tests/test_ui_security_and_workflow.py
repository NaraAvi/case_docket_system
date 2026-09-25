from app import create_app


def test_ui_routes_redirect_without_an_active_session_cookie():
    app = create_app(testing=True)
    client = app.test_client()

    for route in [
        "/citizen",
        "/citizen/dockets/new",
        "/constable",
        "/detective",
        "/station-commander",
        "/ipid",
        "/active-cases",
        "/evidence-vault",
    ]:
        response = client.get(route, follow_redirects=False)
        assert response.status_code == 302, f"{route} should redirect to login without a session"
        assert response.headers["Location"].endswith("/login"), f"{route} should redirect to /login"


def test_citizen_to_constable_deterministic_workflow_runs_via_api():
    app = create_app(testing=True)
    client = app.test_client()

    citizen_login = client.post(
        "/api/v1/auth/login",
        json={"test_id": "2200223333111"},
    )
    assert citizen_login.status_code == 200, citizen_login.get_data(as_text=True)
    citizen_token = citizen_login.get_json()["access_token"]

    from tests.conftest import create_case_via_service

    case = create_case_via_service(
        client,
        "2200223333111",
        "Broken gate at main entrance",
        "The public gate at the main entrance was physically damaged and the lock mechanism no longer secures the site.",
        incident_date="2026-09-01",
        location="Main Entrance, Springfield Sector 4",
    )
    case_reference = case["case_reference"]

    statement = client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        json={"statement_text": "The lock mechanism was damaged and the gate remained unsecured overnight."},
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert statement.status_code == 201, statement.get_data(as_text=True)

    submitted = client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert submitted.status_code == 200, submitted.get_data(as_text=True)

    constable_login = client.post(
        "/api/v1/auth/login",
        json={"test_id": "2200223333114"},
    )
    assert constable_login.status_code == 200, constable_login.get_data(as_text=True)
    constable_token = constable_login.get_json()["access_token"]

    queue = client.get(
        "/api/v1/constable/dockets/unregistered",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert queue.status_code == 200, queue.get_data(as_text=True)
    assert any(item["case_reference"] == case_reference for item in queue.get_json())

    open_docket = client.get(
        f"/api/v1/constable/dockets/{case_reference}",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert open_docket.status_code == 200, open_docket.get_data(as_text=True)

    interview = client.post(
        f"/api/v1/constable/dockets/{case_reference}/interview",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert interview.status_code == 201, interview.get_data(as_text=True)
    interview_id = interview.get_json()["interview_id"]

    citizen_recording = client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        json={"filename": "citizen.wav", "storage_reference": "citizen.wav"},
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert citizen_recording.status_code == 201, citizen_recording.get_data(as_text=True)

    constable_recording = client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        json={"filename": "constable.wav", "storage_reference": "constable.wav"},
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert constable_recording.status_code == 201, constable_recording.get_data(as_text=True)

    registered = client.post(
        f"/api/v1/constable/interviews/{interview_id}/register",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert registered.status_code == 200, registered.get_data(as_text=True)
    assert registered.get_json()["status"] == "REGISTERED"
