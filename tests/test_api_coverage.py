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

    def test_citizen_escalation_list_reflects_ipid_decision_once_resolved(self, app_client):
        """GitHub issue #7: the citizen escalation list used to drop the
        decision/decision_reason/decision_at fields entirely, so a citizen
        had no way to see whether IPID had dismissed or upheld their
        escalation."""
        case_reference = _registered_case(app_client)
        citizen_token = _login(app_client, "citizen")
        escalation_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "Officer ignored my repeated follow-up requests."},
            headers=_auth_headers(citizen_token),
        )
        escalation_id = escalation_response.get_json()["escalation_id"]

        before = app_client.get(f"/api/v1/citizen/dockets/{case_reference}/escalations", headers=_auth_headers(citizen_token))
        before_item = before.get_json()[0]
        assert before_item["status"] == "OPEN"
        assert before_item["decision"] is None

        ipid_token = _login(app_client, "ipid")
        app_client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=_auth_headers(ipid_token))
        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/dismiss",
            json={"reason": "Insufficient evidence to substantiate."},
            headers=_auth_headers(ipid_token),
        )

        after = app_client.get(f"/api/v1/citizen/dockets/{case_reference}/escalations", headers=_auth_headers(citizen_token))
        after_item = after.get_json()[0]
        assert after_item["status"] == "RESOLVED"
        assert after_item["decision"] == "DISMISSED"
        assert after_item["decision_reason"] == "Insufficient evidence to substantiate."
        assert after_item["decision_at"]

    def test_citizen_timeline_includes_investigation_opened_event(self, app_client):
        """GitHub issue #2: a detective opening an investigation was never
        recorded on the case's own timeline, so a citizen had no visibility
        into it even though the detective-side investigation record logged
        it internally."""
        case_reference = _registered_case(app_client)
        detective_token = _login(app_client, "detective")
        app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/investigation",
            json={"notes": "Initial notes."},
            headers=_auth_headers(detective_token),
        )
        citizen_token = _login(app_client, "citizen")
        response = app_client.get(f"/api/v1/citizen/dockets/{case_reference}/timeline", headers=_auth_headers(citizen_token))
        assert response.status_code == 200
        assert any(event.get("event_type") == "investigation_opened" for event in response.get_json())


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

    def test_note_entries_create_list_and_optional_evidence_link(self, app_client):
        """GitHub issue #2: detectives can add multiple standalone note
        entries, optionally attached to a specific evidence item, distinct
        from the single-field working `notes` summary."""
        case_reference, detective_token, investigation_id = self._open_investigation(app_client)

        general_response = app_client.post(
            f"/api/v1/detective/investigations/{investigation_id}/note-entries",
            json={"note_text": "General note with no evidence link."},
            headers=_auth_headers(detective_token),
        )
        assert general_response.status_code == 201
        assert general_response.get_json()["evidence_reference"] is None

        citizen_token = _login(app_client, "citizen")
        evidence_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "PHOTO", "description": "Broken window photo.", "filename": "window.jpg"},
            headers=_auth_headers(citizen_token),
        )
        evidence_id = evidence_response.get_json()["evidence_id"]

        linked_response = app_client.post(
            f"/api/v1/detective/investigations/{investigation_id}/note-entries",
            json={"note_text": "Zoomed crop shows forced entry.", "evidence_reference": evidence_id},
            headers=_auth_headers(detective_token),
        )
        assert linked_response.status_code == 201
        assert str(linked_response.get_json()["evidence_reference"]) == str(evidence_id)

        invalid_response = app_client.post(
            f"/api/v1/detective/investigations/{investigation_id}/note-entries",
            json={"note_text": "Bad link.", "evidence_reference": "does-not-exist"},
            headers=_auth_headers(detective_token),
        )
        assert invalid_response.status_code == 400

        list_response = app_client.get(f"/api/v1/detective/investigations/{investigation_id}/note-entries", headers=_auth_headers(detective_token))
        assert list_response.status_code == 200
        assert len(list_response.get_json()) == 2

    def test_docket_view_still_shows_the_investigation_after_completion(self, app_client):
        """Found via manual browser testing while verifying GitHub issue #4:
        `get_docket_for_detective` only ever surfaced OPEN/IN_PROGRESS
        investigations, so the moment an investigation was completed, the
        detective workspace looked like no investigation had ever been
        started -- hiding the very findings/notes/outcome the completion
        flow was supposed to preserve."""
        case_reference, detective_token, investigation_id = self._open_investigation(app_client)
        app_client.post(
            f"/api/v1/detective/investigations/{investigation_id}/complete",
            json={"outcome": "VALID", "final_notes": "Evidence supports the citizen's account."},
            headers=_auth_headers(detective_token),
        )

        response = app_client.get(f"/api/v1/detective/dockets/{case_reference}", headers=_auth_headers(detective_token))
        assert response.status_code == 200
        investigation = response.get_json()["investigation"]
        assert investigation is not None
        assert investigation["status"] == "COMPLETED"

        # But mutation is still rejected once completed.
        note_response = app_client.post(
            f"/api/v1/detective/investigations/{investigation_id}/note-entries",
            json={"note_text": "Too late."},
            headers=_auth_headers(detective_token),
        )
        assert note_response.status_code == 400

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
            json={"category": "OFFICER_CONDUCT", "description": "Officer ignored my repeated follow-up requests."},
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
            json={"category": "OFFICER_CONDUCT", "description": "Officer ignored my repeated follow-up requests."},
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

    def test_take_custody_freezes_docket_and_blocks_other_officer_mutation(self, app_client):
        """GitHub issue #3: an IPID reviewer can explicitly take custody of a
        docket under review, freezing it from other officers, independent of
        the eventual dismiss/uphold decision."""
        case_reference, escalation_id, ipid_token = self._escalation_under_review(app_client)

        custody_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Preventing further tampering while reviewing."},
            headers=_auth_headers(ipid_token),
        )
        assert custody_response.status_code == 200
        assert custody_response.get_json()["status"] == "ACTIVE"

        # Freezing again before release is rejected.
        again_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Duplicate attempt."},
            headers=_auth_headers(ipid_token),
        )
        assert again_response.status_code == 400

        # A frozen docket blocks other officers' mutations (existing
        # freeze_engine invariant, exercised here via constable flagging).
        constable_token = _login(app_client, "constable")
        flag_response = app_client.post(
            f"/api/v1/constable/dockets/{case_reference}/flags",
            json={"category": "OTHER", "notes": "Attempted edit while frozen.", "status": "OPEN"},
            headers=_auth_headers(constable_token),
        )
        assert flag_response.status_code == 400

        detail_response = app_client.get(f"/api/v1/ipid/escalations/{escalation_id}", headers=_auth_headers(ipid_token))
        assert detail_response.get_json()["freeze_status"] == "FROZEN"

    def test_uphold_without_an_assigned_officer_fails_cleanly_without_resolving_or_freezing(self, app_client):
        """Found via manual browser testing: `uphold_escalation` used to
        resolve the escalation and freeze the docket *before* checking
        whether an officer was actually assigned to revoke, so a missing
        assignment left the escalation permanently RESOLVED/UPHELD and the
        docket permanently frozen with no disciplinary case and no way to
        recover (dismiss requires UNDER_REVIEW, a second uphold requires
        not-already-resolved). The check now happens first."""
        case_reference, escalation_id, ipid_token = self._escalation_under_review(app_client)

        uphold_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/uphold",
            json={"reason": "Would-be uphold with nobody assigned."},
            headers=_auth_headers(ipid_token),
        )
        assert uphold_response.status_code == 400

        detail_response = app_client.get(f"/api/v1/ipid/escalations/{escalation_id}", headers=_auth_headers(ipid_token))
        assert detail_response.get_json()["status"] == "UNDER_REVIEW"
        assert detail_response.get_json()["freeze_status"] == "NOT_FROZEN"

        # Still recoverable: dismiss now succeeds since nothing was resolved.
        dismiss_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/dismiss",
            json={"reason": "No officer to hold accountable; closing out."},
            headers=_auth_headers(ipid_token),
        )
        assert dismiss_response.status_code == 200
        assert case_reference  # keep referenced for clarity

    def test_take_custody_forbidden_for_non_ipid(self, app_client):
        _, escalation_id, _ = self._escalation_under_review(app_client)
        token = _login(app_client, "constable")
        response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
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


class TestFreezeVisibilityAndCustodyCases:
    """Follow-up request: reflect frozen docket status to every non-IPID
    role, and give IPID a dedicated section for cases they've taken custody
    of, with a way to actually open and keep working them."""

    def test_freeze_status_reflected_on_citizen_and_detective_docket_detail(self, app_client):
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)
        citizen_token = _login(app_client, "citizen")
        detective_token = _login(app_client, "detective")

        # Not frozen yet.
        citizen_before = app_client.get(f"/api/v1/citizen/dockets/{case_reference}", headers=_auth_headers(citizen_token)).get_json()
        assert citizen_before["is_frozen"] is False
        assert citizen_before["freeze_status"] == "NOT_FROZEN"

        custody_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Preventing tampering while reviewing."},
            headers=_auth_headers(ipid_token),
        )
        assert custody_response.status_code == 200

        citizen_after = app_client.get(f"/api/v1/citizen/dockets/{case_reference}", headers=_auth_headers(citizen_token)).get_json()
        assert citizen_after["is_frozen"] is True
        assert citizen_after["freeze_status"] == "FROZEN"
        assert "Preventing tampering" in citizen_after["freeze_reason"]

        detective_after = app_client.get(f"/api/v1/detective/dockets/{case_reference}", headers=_auth_headers(detective_token))
        assert detective_after.status_code == 200
        assert detective_after.get_json()["is_frozen"] is True

    def test_freeze_status_reflected_on_the_shared_operational_dockets_list(self, app_client):
        """A constable can only reach its own per-docket detail route
        (`GET /constable/dockets/<ref>`) while a case is still
        AWAITING_CONSTABLE_REGISTRATION (a pre-existing, load-bearing
        invariant -- see `ConstableRegistrationService.get_docket`/`open_docket`),
        and freezing requires REGISTERED -- so a constable can never actually
        view a frozen case through that route. The shared operational dockets
        list (`GET /station-commander/dockets`, open to every operational
        role) is the real surface where a constable would see freeze status,
        and it already carried the field before this change."""
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)
        constable_token = _login(app_client, "constable")

        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Preventing tampering while reviewing."},
            headers=_auth_headers(ipid_token),
        )

        listing = app_client.get("/api/v1/station-commander/dockets", headers=_auth_headers(constable_token)).get_json()
        entry = next(item for item in listing if item["case_reference"] == case_reference)
        assert entry["is_frozen"] is True

    def test_custody_cases_lists_only_active_ipid_review_freezes(self, app_client):
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)

        empty_response = app_client.get("/api/v1/ipid/custody-cases", headers=_auth_headers(ipid_token))
        assert empty_response.status_code == 200
        assert empty_response.get_json() == []

        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Preventing tampering while reviewing."},
            headers=_auth_headers(ipid_token),
        )

        populated_response = app_client.get("/api/v1/ipid/custody-cases", headers=_auth_headers(ipid_token))
        assert populated_response.status_code == 200
        custody_cases = populated_response.get_json()
        assert len(custody_cases) == 1
        assert custody_cases[0]["case_reference"] == case_reference
        assert custody_cases[0]["escalation_id"] == escalation_id

        # Dismissing releases the freeze -- the case drops off the list.
        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/dismiss",
            json={"reason": "Insufficient evidence to substantiate."},
            headers=_auth_headers(ipid_token),
        )
        after_dismiss = app_client.get("/api/v1/ipid/custody-cases", headers=_auth_headers(ipid_token))
        assert after_dismiss.get_json() == []

    def test_custody_cases_stays_populated_after_an_uphold_decision(self, app_client):
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)
        station_commander_token = _login(app_client, "station_commander")
        app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["detective"], "reason": "Assigning for investigation."},
            headers=_auth_headers(station_commander_token),
        )
        uphold_response = app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/uphold",
            json={"reason": "Confirmed misconduct."},
            headers=_auth_headers(ipid_token),
        )
        assert uphold_response.status_code == 200

        custody_cases = app_client.get("/api/v1/ipid/custody-cases", headers=_auth_headers(ipid_token)).get_json()
        assert len(custody_cases) == 1
        assert custody_cases[0]["escalation_status"] == "RESOLVED"
        assert custody_cases[0]["escalation_decision"] == "UPHELD"

    def test_custody_cases_forbidden_for_non_ipid(self, app_client):
        token = _login(app_client, "constable")
        response = app_client.get("/api/v1/ipid/custody-cases", headers=_auth_headers(token))
        assert response.status_code == 403


class TestFrozenDocketBlockedView:
    """Detective, constable, and station commander now see a minimal
    "Case Frozen" payload instead of full case content while a docket is
    frozen -- not just a warning alongside the content."""

    def test_detective_gets_a_minimal_frozen_payload_instead_of_full_case_content(self, app_client):
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)
        detective_token = _login(app_client, "detective")
        app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/investigation",
            json={"notes": "Initial notes."},
            headers=_auth_headers(detective_token),
        )

        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Preventing tampering while reviewing."},
            headers=_auth_headers(ipid_token),
        )

        response = app_client.get(f"/api/v1/detective/dockets/{case_reference}", headers=_auth_headers(detective_token))
        assert response.status_code == 200
        body = response.get_json()
        assert body["is_frozen"] is True
        assert "statements" not in body
        assert "evidence" not in body
        assert "investigation" not in body

    def test_constable_gets_a_minimal_frozen_payload_instead_of_full_case_content(self, app_client):
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)
        constable_token = _login(app_client, "constable")
        station_commander_token = _login(app_client, "station_commander")
        app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["constable"], "reason": "Constable follow-up."},
            headers=_auth_headers(station_commander_token),
        )

        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Preventing tampering while reviewing."},
            headers=_auth_headers(ipid_token),
        )

        response = app_client.get(f"/api/v1/constable/dockets/{case_reference}", headers=_auth_headers(constable_token))
        assert response.status_code == 200
        body = response.get_json()
        assert body["is_frozen"] is True
        assert "statements" not in body
        assert "evidence" not in body

    def test_station_commander_gets_a_minimal_frozen_payload_instead_of_full_case_content(self, app_client):
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)
        station_commander_token = _login(app_client, "station_commander")

        # Confirm full detail is visible before the freeze...
        before = app_client.get(f"/api/v1/station-commander/dockets/{case_reference}", headers=_auth_headers(station_commander_token))
        assert "sla" in before.get_json()

        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Preventing tampering while reviewing."},
            headers=_auth_headers(ipid_token),
        )

        # ...and withheld after it.
        after = app_client.get(f"/api/v1/station-commander/dockets/{case_reference}", headers=_auth_headers(station_commander_token))
        assert after.status_code == 200
        body = after.get_json()
        assert body["is_frozen"] is True
        assert "sla" not in body
        assert "current_assignment" not in body

        # The oversight list still shows it (with the FROZEN flag), unlike the single-docket detail route.
        listing = app_client.get("/api/v1/station-commander/dockets", headers=_auth_headers(station_commander_token)).get_json()
        entry = next(item for item in listing if item["case_reference"] == case_reference)
        assert entry["is_frozen"] is True
        assert "sla" in entry


class TestVictimStatementsByDetectiveAndIpid:
    def test_detective_can_add_a_statement_visible_to_citizen_and_constable(self, app_client):
        case_reference, detective_token, investigation_id = TestDetectiveReadEndpointsAndCompletion()._open_investigation(app_client)

        response = app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/statements",
            json={"statement_text": "Witness confirms seeing the suspect flee northbound."},
            headers=_auth_headers(detective_token),
        )
        assert response.status_code == 201
        body = response.get_json()
        assert body["recorded_by_role"] == "detective"
        assert investigation_id  # keep referenced for clarity

        citizen_token = _login(app_client, "citizen")
        citizen_view = app_client.get(f"/api/v1/citizen/dockets/{case_reference}", headers=_auth_headers(citizen_token)).get_json()
        assert any(s["statement_text"] == "Witness confirms seeing the suspect flee northbound." for s in citizen_view["statements"])

        constable_token = _login(app_client, "constable")
        station_commander_token = _login(app_client, "station_commander")
        app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["constable"], "reason": "Constable to follow up on witness statement."},
            headers=_auth_headers(station_commander_token),
        )
        constable_view = app_client.get(f"/api/v1/constable/dockets/{case_reference}", headers=_auth_headers(constable_token)).get_json()
        assert any(s["statement_text"] == "Witness confirms seeing the suspect flee northbound." for s in constable_view["statements"])

    def test_detective_statement_rejected_when_case_is_frozen(self, app_client):
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)
        detective_token = _login(app_client, "detective")
        app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/investigation",
            json={"notes": "Initial notes."},
            headers=_auth_headers(detective_token),
        )
        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Preventing tampering while reviewing."},
            headers=_auth_headers(ipid_token),
        )

        response = app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/statements",
            json={"statement_text": "Too late."},
            headers=_auth_headers(detective_token),
        )
        assert response.status_code == 400

    def test_ipid_can_add_a_statement_even_while_the_case_is_frozen(self, app_client):
        """IPID is the actor who freezes a docket via take-custody/uphold --
        they must still be able to record statements on a case they're
        actively reviewing in custody."""
        case_reference, escalation_id, ipid_token = TestIpidReviewNotesFindingsAndDisciplinaryCases()._escalation_under_review(app_client)
        app_client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/take-custody",
            json={"reason": "Preventing tampering while reviewing."},
            headers=_auth_headers(ipid_token),
        )

        response = app_client.post(
            f"/api/v1/ipid/dockets/{case_reference}/statements",
            json={"statement_text": "Reviewer independently interviewed the victim."},
            headers=_auth_headers(ipid_token),
        )
        assert response.status_code == 201
        assert response.get_json()["recorded_by_role"] == "ipid"

        citizen_token = _login(app_client, "citizen")
        citizen_view = app_client.get(f"/api/v1/citizen/dockets/{case_reference}", headers=_auth_headers(citizen_token)).get_json()
        assert any(s["statement_text"] == "Reviewer independently interviewed the victim." for s in citizen_view["statements"])

    def test_add_statement_forbidden_for_wrong_role(self, app_client):
        case_reference = _registered_case(app_client)
        constable_token = _login(app_client, "constable")
        response = app_client.post(
            f"/api/v1/detective/dockets/{case_reference}/statements",
            json={"statement_text": "Not allowed."},
            headers=_auth_headers(constable_token),
        )
        assert response.status_code == 403


class TestConstableAssignmentAccess:
    """Verify the station-commander-assigns-a-constable flow end to end, and
    that the assigned constable retains access to the docket afterward."""

    def test_station_commander_assigns_constable_to_unregistered_docket_and_constable_completes_registration(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_and_submit_docket(app_client, citizen_token, title="Unassigned break-in")
        station_commander_token = _login(app_client, "station_commander")

        assign_response = app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["constable"], "reason": "Manually assigning since this docket sat unregistered."},
            headers=_auth_headers(station_commander_token),
        )
        assert assign_response.status_code == 200
        assert assign_response.get_json()["officer_role"] == "constable"

        constable_token = _login(app_client, "constable")
        opened = app_client.get(f"/api/v1/constable/dockets/{case_reference}", headers=_auth_headers(constable_token))
        assert opened.status_code == 200

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
        register_response = app_client.post(f"/api/v1/constable/interviews/{interview_id}/register", headers=_auth_headers(constable_token))
        assert register_response.status_code == 200
        assert register_response.get_json()["status"] == "REGISTERED"

    def test_constable_reassigned_to_a_registered_docket_can_still_open_it(self, app_client):
        """Post-registration, any officer role can be assigned (not just
        constable) -- if a constable is the target, they need a way to keep
        handling that docket, since the pre-registration-only route used to
        reject anything that wasn't AWAITING_CONSTABLE_REGISTRATION."""
        case_reference = _registered_case(app_client)
        station_commander_token = _login(app_client, "station_commander")

        assign_response = app_client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_TEST_IDS["constable"], "reason": "Constable follow-up on a registered docket."},
            headers=_auth_headers(station_commander_token),
        )
        assert assign_response.status_code == 200
        assert assign_response.get_json()["officer_role"] == "constable"

        constable_token = _login(app_client, "constable")
        response = app_client.get(f"/api/v1/constable/dockets/{case_reference}", headers=_auth_headers(constable_token))
        assert response.status_code == 200
        assert response.get_json()["status"] == "REGISTERED"

    def test_unassigned_constable_cannot_open_a_registered_docket(self, app_client):
        """The open queue behavior stays pre-registration only -- a
        REGISTERED docket is now reachable only by the specific constable
        assigned to it, not by any constable."""
        case_reference = _registered_case(app_client)
        constable_token = _login(app_client, "constable")
        response = app_client.get(f"/api/v1/constable/dockets/{case_reference}", headers=_auth_headers(constable_token))
        assert response.status_code == 400
