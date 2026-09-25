from flask_jwt_extended import create_access_token

from app import create_app


def set_role_cookie(app, client, role, test_id, full_name=None):
    with app.app_context():
        token = create_access_token(
            identity=str(test_id),
            additional_claims={
                "role": role,
                "full_name": full_name or f"Demo {role.title()}",
                "active": True,
            },
        )
    client.set_cookie(key="pdas_session_token", value=token, domain="localhost")
    return token


def test_login_route_renders_without_session():
    app = create_app(testing=True)
    client = app.test_client()

    response = client.get("/login")
    assert response.status_code == 200


def test_role_dashboard_routes_redirect_without_session():
    app = create_app(testing=True)
    client = app.test_client()

    routes = [
        "/citizen",
        "/citizen/dockets/new",
        "/constable",
        "/detective",
        "/station-commander",
        "/ipid",
        "/active-cases",
        "/evidence-vault",
    ]

    for route in routes:
        response = client.get(route, follow_redirects=False)
        assert response.status_code == 302, f"{route} should redirect to login without a session"
        assert response.headers["Location"].endswith("/login"), f"{route} should redirect to /login"


def test_authenticated_role_dashboard_routes_render():
    app = create_app(testing=True)
    client = app.test_client()

    route_map = {
        "/citizen": ("citizen", "2200223333111"),
        "/citizen/dockets/new": ("citizen", "2200223333111"),
        "/constable": ("constable", "2200223333114"),
        "/detective": ("detective", "2200223333115"),
        "/station-commander": ("station_commander", "2200223333116"),
        "/ipid": ("ipid", "2200223333117"),
        "/active-cases": ("constable", "2200223333114"),
        "/evidence-vault": ("station_commander", "2200223333116"),
    }

    for route, (role, test_id) in route_map.items():
        set_role_cookie(app, client, role, test_id)
        response = client.get(route)
        assert response.status_code == 200, f"{route} should render successfully for a valid session"


def test_authenticated_workflow_detail_routes_render():
    app = create_app(testing=True)
    client = app.test_client()

    route_map = {
        "/constable/dockets/CD-1000": ("constable", "2200223333114"),
        "/detective/dockets/CD-1000": ("detective", "2200223333115"),
        "/station-commander/dockets/CD-1000": ("station_commander", "2200223333116"),
        "/ipid/escalations/ESC-1000": ("ipid", "2200223333117"),
    }

    for route, (role, test_id) in route_map.items():
        set_role_cookie(app, client, role, test_id)
        response = client.get(route)
        assert response.status_code == 200, f"{route} should render successfully for a valid session"
