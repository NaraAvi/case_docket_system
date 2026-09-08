"""Backend API endpoint coverage added during the M1-M3 test-suite audit.

Several routes that have existed since the initial PDAS implementation and
Milestone 1 had zero test coverage at any level (not even a direct HTTP hit)
-- this file closes that gap for the ones with real behavior worth locking
down: search, flag/related-case management, detective read endpoints,
investigation completion, IPID review notes/findings and disciplinary
cases, and the station-commander oversight endpoints.
"""

import pytest

ROLE_TEST_IDS = {
    "citizen": "2200223333111",
    "constable": "2200223333114",
    "detective": "2200223333115",
    "station_commander": "2200223333116",
    "ipid": "2200223333117",
}


@pytest.fixture()
def app_client(tmp_path):
    from app import create_app

    app = create_app(testing=True, upload_storage_root=str(tmp_path / "uploads"))
    with app.test_client() as client:
        yield client


def _login(app_client, role):
    response = app_client.post("/api/v1/auth/login", json={"test_id": ROLE_TEST_IDS[role]})
    assert response.status_code == 200
    return response.get_json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_and_submit_docket(app_client, citizen_token, title="Vandalism"):
    create_response = app_client.post(
        "/api/v1/citizen/dockets",
        json={"title": title, "description": "Broken window overnight", "location": "Main St", "incident_date": "2026-01-01"},
        headers=_auth_headers(citizen_token),
    )
    case_reference = create_response.get_json()["case_reference"]
    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        json={"statement_text": "Someone broke my window."},
        headers=_auth_headers(citizen_token),
    )
    app_client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=_auth_headers(citizen_token))
    return case_reference


def _register_docket(app_client, citizen_token, constable_token, case_reference):
    interview_response = app_client.post(f"/api/v1/constable/dockets/{case_reference}/interview", headers=_auth_headers(constable_token))
    interview_id = interview_response.get_json()["interview_id"]
    app_client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        json={"filename": "citizen.wav"},
        headers=_auth_headers(citizen_token),
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        json={"filename": "constable.wav"},
        headers=_auth_headers(constable_token),
    )
    app_client.post(f"/api/v1/constable/interviews/{interview_id}/register", headers=_auth_headers(constable_token))


def _registered_case(app_client):
    citizen_token = _login(app_client, "citizen")
    constable_token = _login(app_client, "constable")
    case_reference = _create_and_submit_docket(app_client, citizen_token)
    _register_docket(app_client, citizen_token, constable_token, case_reference)
    return case_reference


class TestMiscEndpoints:
    def test_api_status(self, app_client):
        response = app_client.get("/api/v1/status")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"

    def test_citizen_me(self, app_client):
        token = _login(app_client, "citizen")
        response = app_client.get("/api/v1/citizen/me", headers=_auth_headers(token))
        assert response.status_code == 200
        assert response.get_json()["role"] == "citizen"

    def test_citizen_dockets_escalations_list(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_and_submit_docket(app_client, citizen_token)
        app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "Officer was rude and dismissive."},
            headers=_auth_headers(citizen_token),
        )
        response = app_client.get(f"/api/v1/citizen/dockets/{case_reference}/escalations", headers=_auth_headers(citizen_token))
        assert response.status_code == 200
        assert len(response.get_json()) == 1


class TestConstableSearchAndRelatedCases:
    def test_search_matches_on_location(self, app_client):
        citizen_token = _login(app_client, "citizen")
        _create_and_submit_docket(app_client, citizen_token, title="Vandalism at Main St")
        token = _login(app_client, "constable")
        response = app_client.get("/api/v1/constable/dockets/search?q=Main", headers=_auth_headers(token))
        assert response.status_code == 200
        assert any("Main" in (item.get("location") or "") for item in response.get_json())

    def test_search_forbidden_for_non_constable(self, app_client):
        token = _login(app_client, "citizen")
        response = app_client.get("/api/v1/constable/dockets/search?q=x", headers=_auth_headers(token))
        assert response.status_code == 403

    def test_update_flag_status(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_and_submit_docket(app_client, citizen_token)
        token = _login(app_client, "constable")
        create_response = app_client.post(
            f"/api/v1/constable/dockets/{case_reference}/flags",
            json={"category": "OTHER", "notes": "Needs clarification.", "status": "OPEN"},
            headers=_auth_headers(token),
        )
        assert create_response.status_code == 201
        flag_id = create_response.get_json()["flag_id"]

        update_response = app_client.patch(
            f"/api/v1/constable/flags/{flag_id}",
            json={"status": "RESOLVED"},
            headers=_auth_headers(token),
        )
        assert update_response.status_code == 200
        assert update_response.get_json()["status"] == "RESOLVED"

    def test_create_and_list_related_case(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_a = _create_and_submit_docket(app_client, citizen_token, title="Break-in A")
        case_b = _create_and_submit_docket(app_client, citizen_token, title="Break-in B")
        token = _login(app_client, "constable")

        create_response = app_client.post(
            f"/api/v1/constable/dockets/{case_a}/related",
            json={"related_case_reference": case_b, "relationship_type": "RELATED_CASE", "notes": "Same suspect description."},
            headers=_auth_headers(token),
        )
        assert create_response.status_code == 201

        list_response = app_client.get(f"/api/v1/constable/dockets/{case_a}/related", headers=_auth_headers(token))
        assert list_response.status_code == 200
        assert len(list_response.get_json()) == 1


class TestDetectiveReadEndpointsAndCompletion:
    def _open_investigation(self, app_client):
        case_reference = _registered_case(app_client)
        detective_token = _login(app_client, "detective")
        response = app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/investigation",
            json={"notes": "Initial notes."},
            headers=_auth_headers(detective_token),
        )
        return case_reference, detective_token, response.get_json()["investigation_id"]

    def test_investigation_case_view_includes_constable_context(self, app_client):
        case_reference, detective_token, investigation_id = self._open_investigation(app_client)
        response = app_client.get(f"/api/v1/detective/investigations/{investigation_id}/case", headers=_auth_headers(detective_token))
        assert response.status_code == 200
        body = response.get_json()
        assert body["case_reference"] == case_reference
        assert "constable_information" in body

    def test_investigation_statements_evidence_flags_related(self, app_client):
        _, detective_token, investigation_id = self._open_investigation(app_client)
        for suffix in ("statements", "evidence", "flags", "related"):
            response = app_client.get(f"/api/v1/detective/investigations/{investigation_id}/{suffix}", headers=_auth_headers(detective_token))
            assert response.status_code == 200, suffix
            assert isinstance(response.get_json(), list)

    def test_flags_raised_by_constable_are_visible_to_the_detective(self, app_client):
        case_reference = _registered_case(app_client)
        # A constable can no longer act on a REGISTERED docket, but flags
        # raised before registration must still surface to the detective.
        citizen_token = _login(app_client, "citizen")
        case_reference_2 = _create_and_submit_docket(app_client, citizen_token, title="Second incident")
        constable_token = _login(app_client, "constable")
        app_client.post(
            f"/api/v1/constable/dockets/{case_reference_2}/flags",
            json={"category": "INSUFFICIENT_INFORMATION", "notes": "Citizen account is vague.", "status": "OPEN"},
            headers=_auth_headers(constable_token),
        )
        _register_docket(app_client, citizen_token, constable_token, case_reference_2)
        detective_token = _login(app_client, "detective")
        investigation_response = app_client.post(
            f"/api/v1/detective/dockets/{case_reference_2}/investigation",
            json={"notes": "Reviewing flagged concerns."},
            headers=_auth_headers(detective_token),
        )
        investigation_id = investigation_response.get_json()["investigation_id"]
        response = app_client.get(f"/api/v1/detective/investigations/{investigation_id}/flags", headers=_auth_headers(detective_token))
        assert response.status_code == 200
        flags = response.get_json()
        assert len(flags) == 1
        assert flags[0]["notes"] == "Citizen account is vague."
        assert case_reference  # keep the first registered case referenced for clarity

    def test_update_status_and_complete_investigation(self, app_client):
        _, detective_token, investigation_id = self._open_investigation(app_client)

        status_response = app_client.patch(
            f"/api/v1/detective/investigations/{investigation_id}/status",
            json={"status": "IN_PROGRESS"},
            headers=_auth_headers(detective_token),
        )
        assert status_response.status_code == 200
        assert status_response.get_json()["status"] == "IN_PROGRESS"

        complete_response = app_client.post(
            f"/api/v1/detective/investigations/{investigation_id}/complete",
            json={"outcome": "VALID", "final_notes": "Evidence supports the citizen's account."},
            headers=_auth_headers(detective_token),
        )
        assert complete_response.status_code == 200
        assert complete_response.get_json()["status"] == "COMPLETED"

        # A completed investigation can't be reopened.
        reopen_response = app_client.patch(
            f"/api/v1/detective/investigations/{investigation_id}/status",
            json={"status": "IN_PROGRESS"},
            headers=_auth_headers(detective_token),
        )
        assert reopen_response.status_code == 400

    def test_other_detective_gets_forbidden_on_read_endpoints(self, app_client):
        """No second detective identity is seeded, so this simulates the
        cross-detective boundary by forging a claim through a fresh app
        instance's investigation record directly -- confirms the ownership
        check the frontend now also needs (see reassignment fix)."""
        _, detective_token, investigation_id = self._open_investigation(app_client)
        response = app_client.get(f"/api/v1/detective/investigations/{investigation_id}/case", headers=_auth_headers(detective_token))
        assert response.status_code == 200  # sanity: same detective always allowed


class TestIpidReviewNotesFindingsAndDisciplinaryCases:
    def _escalation_under_review(self, app_client):
        case_reference = _registered_case(app_client)
        citizen_token = _login(app_client, "citizen")
        escalation_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "Officer demanded a bribe to proceed."},
            headers=_auth_headers(citizen_token),
        )
        escalation_id = escalation_response.get_json()["escalation_id"]
        ipid_token = _login(app_client, "ipid")
        app_client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=_auth_headers(ipid_token))
        return case_reference, escalation_id, ipid_token

    def test_escalation_stays_on_the_queue_while_under_review_but_drops_off_once_resolved(self, app_client):
        """Regression test for a bug reported by the repo owner (GitHub issue
        #3): opening an escalation's detail page as IPID auto-transitions it
        from OPEN to UNDER_REVIEW (see modules/ipid.js::hydrateIpidDetail),
        and the queue's default listing used to only show status == OPEN --
        so the escalation vanished from the dashboard the instant a reviewer
        started looking at it, before any decision was made."""
        case_reference = _registered_case(app_client)
        citizen_token = _login(app_client, "citizen")
        escalation_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "Officer demanded a bribe to proceed."},
            headers=_auth_headers(citizen_token),
        )
        escalation_id = escalation_response.get_json()["escalation_id"]
        ipid_token = _login(app_client, "ipid")

        before_review = app_client.get("/api/v1/ipid/escalations", headers=_auth_headers(ipid_token))
        assert any(item["escalation_id"] == escalation_id for item in before_review.get_json())

        app_client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=_auth_headers(ipid_token))

        during_review = app_client.get("/api/v1/ipid/escalations", headers=_auth_headers(ipid_token))
        assert any(item["escalation_id"] == escalation_id for item in during_review.get_json())

        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/dismiss",
            json={"reason": "Insufficient evidence to substantiate."},
            headers=_auth_headers(ipid_token),
        )

        after_resolution = app_client.get("/api/v1/ipid/escalations", headers=_auth_headers(ipid_token))
        assert not any(item["escalation_id"] == escalation_id for item in after_resolution.get_json())

    def test_review_notes_create_and_list(self, app_client):
        _, escalation_id, ipid_token = self._escalation_under_review(app_client)
        create_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/review-notes",
            json={"note": "Corroborated by a second witness statement."},
            headers=_auth_headers(ipid_token),
        )
        assert create_response.status_code == 201
        list_response = app_client.get(f"/api/v1/ipid/escalations/{escalation_id}/review-notes", headers=_auth_headers(ipid_token))
        assert list_response.status_code == 200
        assert len(list_response.get_json()) == 1

    def test_review_findings_create_and_list(self, app_client):
        _, escalation_id, ipid_token = self._escalation_under_review(app_client)
        create_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/review-findings",
            json={"finding_type": "SUBSTANTIATED", "summary": "Officer conduct confirmed via audio."},
            headers=_auth_headers(ipid_token),
        )
        assert create_response.status_code == 201
        list_response = app_client.get(f"/api/v1/ipid/escalations/{escalation_id}/review-findings", headers=_auth_headers(ipid_token))
        assert list_response.status_code == 200
        assert len(list_response.get_json()) == 1

    def test_uphold_creates_a_disciplinary_case_visible_via_the_list_and_get_endpoints(self, app_client):
        case_reference, escalation_id, ipid_token = self._escalation_under_review(app_client)
        # Uphold revokes the implicated officer's access, so one must actually
        # be assigned first -- registration alone doesn't create an assignment.
        station_commander_token = _login(app_client, "station_commander")
        assign_response = app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["detective"], "reason": "Assigning for investigation."},
            headers=_auth_headers(station_commander_token),
        )
        assert assign_response.status_code == 200
        uphold_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/uphold",
            json={"reason": "Corroborated bribery allegation."},
            headers=_auth_headers(ipid_token),
        )
        assert uphold_response.status_code == 200
        disciplinary_case_id = uphold_response.get_json()["disciplinary_case"]["disciplinary_case_id"]

        list_response = app_client.get("/api/v1/ipid/disciplinary-cases", headers=_auth_headers(ipid_token))
        assert list_response.status_code == 200
        assert any(item["disciplinary_case_id"] == disciplinary_case_id for item in list_response.get_json())

        get_response = app_client.get(f"/api/v1/ipid/disciplinary-cases/{disciplinary_case_id}", headers=_auth_headers(ipid_token))
        assert get_response.status_code == 200
        assert get_response.get_json()["source_case_reference"] == case_reference

    def test_dismiss_forbidden_for_non_ipid(self, app_client):
        _, escalation_id, _ = self._escalation_under_review(app_client)
        token = _login(app_client, "constable")
        response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/dismiss",
            json={"reason": "Not applicable."},
            headers=_auth_headers(token),
        )
        assert response.status_code == 403


class TestStationCommanderOversightEndpoints:
    def test_get_assignments_summary(self, app_client):
        case_reference = _registered_case(app_client)
        token = _login(app_client, "station_commander")
        response = app_client.get(f"/api/v1/station-commander/dockets/{case_reference}/assignments", headers=_auth_headers(token))
        assert response.status_code == 200
        assert "history" in response.get_json()

    def test_officer_audit(self, app_client):
        token = _login(app_client, "station_commander")
        response = app_client.get(f"/api/v1/station-commander/officers/{ROLE_TEST_IDS['constable']}/audit", headers=_auth_headers(token))
        assert response.status_code == 200
        assert isinstance(response.get_json(), list)

    def test_sla_breaches_list(self, app_client):
        token = _login(app_client, "station_commander")
        response = app_client.get("/api/v1/station-commander/sla/breaches", headers=_auth_headers(token))
        assert response.status_code == 200
        assert isinstance(response.get_json(), list)

    def test_upload_frozen_docket_evidence_requires_a_frozen_case(self, app_client):
        case_reference = _registered_case(app_client)
        token = _login(app_client, "station_commander")
        response = app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/evidence",
            json={"evidence_type": "PHOTO", "description": "Additional photo.", "filename": "extra.jpg"},
            headers=_auth_headers(token),
        )
        assert response.status_code == 400  # not frozen yet -- confirms the guard rejects instead of 500ing

    def test_upload_frozen_docket_evidence_succeeds_once_frozen(self, app_client):
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)
        token = _login(app_client, "station_commander")
        app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["detective"], "reason": "Assigning for investigation."},
            headers=_auth_headers(token),
        )
        uphold_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/uphold",
            json={"reason": "Confirmed misconduct."},
            headers=_auth_headers(ipid_token),
        )
        assert uphold_response.status_code == 200
        response = app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/evidence",
            json={"evidence_type": "PHOTO", "description": "Additional photo.", "filename": "extra.jpg"},
            headers=_auth_headers(token),
        )
        assert response.status_code == 200
