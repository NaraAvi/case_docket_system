"""System tests for Milestone 2: the pdas.js monolith -> ES6 module split.

These exercise the real Flask app end-to-end (routing, templates, and the
static file server) rather than the frontend logic in isolation -- that is
covered by the Vitest suite under app/static/js/tests/.
"""

import pytest

ROLE_TEST_IDS = {
    "citizen": "2200223333111",
    "constable": "2200223333114",
    "detective": "2200223333115",
    "station_commander": "2200223333116",
    "ipid": "2200223333117",
}

STATIC_JS_MODULES = [
    "js/pdas_app.js",
    "js/core/api.js",
    "js/core/auth.js",
    "js/core/ui.js",
    "js/modules/citizen.js",
    "js/modules/constable.js",
    "js/modules/detective.js",
    "js/modules/station_commander.js",
    "js/modules/ipid.js",
    "js/modules/shared.js",
]

ROLE_DASHBOARD_ROUTES = {
    "citizen": "/citizen",
    "constable": "/constable",
    "detective": "/detective",
    "station_commander": "/station-commander",
    "ipid": "/ipid",
}


def _login(app_client, role):
    response = app_client.post("/api/v1/auth/login", json={"test_id": ROLE_TEST_IDS[role]})
    assert response.status_code == 200
    token = response.get_json()["access_token"]
    app_client.set_cookie("pdas_session_token", token, path="/")
    return token


class TestStaticModuleFiles:
    """Every new ES6 module must actually be servable by Flask's static route."""

    @pytest.mark.parametrize("path", STATIC_JS_MODULES)
    def test_module_is_served(self, app_client, path):
        response = app_client.get(f"/static/{path}")
        assert response.status_code == 200
        assert len(response.data) > 0
        assert "javascript" in response.content_type or "ecmascript" in response.content_type

    def test_old_monolith_is_gone(self, app_client):
        assert app_client.get("/static/js/pdas.js").status_code == 404
        assert app_client.get("/static/js/citizen_dashboard.js").status_code == 404


class TestBaseTemplateWiring:
    def test_login_page_loads_the_module_entrypoint_not_the_old_monolith(self, app_client):
        response = app_client.get("/login")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert '<script type="module" src="/static/js/pdas_app.js">' in html
        assert "js/pdas.js" not in html


class TestRoleDashboardsStillRenderWithModularScripts:
    """Full-stack regression: login -> role dashboard, for every role, with the
    new module wiring in place (not just the JS unit/integration suite)."""

    @pytest.mark.parametrize("role,route", ROLE_DASHBOARD_ROUTES.items())
    def test_dashboard_renders_for_role(self, app_client, role, route):
        _login(app_client, role)

        response = app_client.get(route)

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert f'data-role="{role}"' in html
        assert '<script type="module" src="/static/js/pdas_app.js">' in html

    def test_unauthenticated_dashboard_access_redirects_to_login(self, app_client):
        response = app_client.get("/citizen")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")


class TestCrossRolePagesLoadTheSharedModuleOnly:
    @pytest.mark.parametrize("role", ROLE_DASHBOARD_ROUTES.keys())
    def test_active_cases_page_renders_for_every_role(self, app_client, role):
        if role == "citizen":
            pytest.skip("Active Cases is restricted to constable/detective/station_commander/ipid.")
        _login(app_client, role)

        response = app_client.get("/active-cases")

        assert response.status_code == 200
        assert "activeCaseList" in response.get_data(as_text=True)
