"""Milestone 4 integration tests: Objective Deterministic Decision Engine.

Covers statutory triage and auto-referral (4.1), SLA / misconduct tiering and
the mandatory sanction matrix (4.2), conflict-of-interest gating (4.3) and the
regulatory / decision read endpoints (4.4).
"""

import pytest

ROLE_TEST_IDS = {
    "citizen": "2200223333111",
    "constable": "2200223333114",
    "detective": "2200223333115",
    "station_commander": "2200223333116",
    "ipid": "2200223333117",
}
BRIBE = "The police officer demanded a bribe to register my case."
NEUTRAL = "Officer ignored my repeated follow-up requests."


@pytest.fixture()
def client(tmp_path):
    from app import create_app

    app = create_app(testing=True, upload_storage_root=str(tmp_path / "uploads"))
    with app.test_client() as test_client:
        yield test_client


def login(client, role):
    response = client.post("/api/v1/auth/login", json={"test_id": ROLE_TEST_IDS[role]})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def submit_docket(client, statement="Someone broke my window."):
    citizen = login(client, "citizen")
    created = client.post(
        "/api/v1/citizen/dockets",
        json={"title": "Vandalism", "description": "Broken window overnight", "location": "Main St", "incident_date": "2026-01-01"},
        headers=citizen,
    )
    case_reference = created.get_json()["case_reference"]
    client.post(f"/api/v1/citizen/dockets/{case_reference}/statements", json={"statement_text": statement}, headers=citizen)
    submitted = client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=citizen)
    return case_reference, submitted


def register(client, case_reference):
    citizen, constable = login(client, "citizen"), login(client, "constable")
    interview = client.post(f"/api/v1/constable/dockets/{case_reference}/interview", headers=constable)
    interview_id = interview.get_json()["interview_id"]
    client.post(f"/api/v1/citizen/interviews/{interview_id}/recording", json={"filename": "c.wav"}, headers=citizen)
    client.post(f"/api/v1/constable/interviews/{interview_id}/recording", json={"filename": "k.wav"}, headers=constable)
    return client.post(f"/api/v1/constable/interviews/{interview_id}/register", headers=constable)


def registered_case(client):
    case_reference, _ = submit_docket(client)
    assert register(client, case_reference).status_code == 200
    return case_reference


def assign(client, case_reference, role="detective"):
    return client.post(
        f"/api/v1/station-commander/dockets/{case_reference}/reassign",
        json={"officer_id": ROLE_TEST_IDS[role], "reason": "Assigning for investigation."},
        headers=login(client, "station_commander"),
    )


def escalate(client, case_reference, text):
    return client.post(
        f"/api/v1/citizen/dockets/{case_reference}/escalations",
        json={"category": "OFFICER_CONDUCT", "description": text},
        headers=login(client, "citizen"),
    )


def custody_cases(client):
    return client.get("/api/v1/ipid/custody-cases", headers=login(client, "ipid")).get_json()


def ipid_escalations(client):
    return client.get("/api/v1/ipid/escalations", headers=login(client, "ipid")).get_json()


def assignments(client, case_reference):
    return client.get(
        f"/api/v1/station-commander/dockets/{case_reference}/assignments", headers=login(client, "station_commander")
    ).get_json()


class TestAutoReferralOnSubmission:
    def test_clean_docket_is_not_referred(self, client):
        case_reference, response = submit_docket(client)
        assert response.status_code == 200
        assert not response.get_json().get("statutory_referral")
        assert custody_cases(client) == []

    def test_s28_text_in_a_statement_auto_refers_and_freezes_before_registration(self, client):
        case_reference, response = submit_docket(client, statement=BRIBE)
        assert response.status_code == 200
        assert response.get_json()["statutory_referral"]
        items = ipid_escalations(client)
        assert len(items) == 1
        item = items[0]
        assert item["case_reference"] == case_reference
        assert item["source"] == "IPID_STATUTORY_MANDATE"
        assert item["statutory_basis"] == "IPID Act 1 of 2011, section 28(1)(g)"
        assert any(case["case_reference"] == case_reference for case in custody_cases(client))

    def test_frozen_docket_cannot_be_registered_by_the_constable(self, client):
        case_reference, _ = submit_docket(client, statement=BRIBE)
        constable = login(client, "constable")
        response = client.post(f"/api/v1/constable/dockets/{case_reference}/interview", headers=constable)
        assert response.status_code == 400
        assert "frozen" in response.get_json()["error"].lower()


class TestAutoReferralOnEscalationAndFlags:
    def test_neutral_citizen_escalation_stays_manual(self, client):
        case_reference = registered_case(client)
        response = escalate(client, case_reference, NEUTRAL)
        assert response.status_code == 201 or response.status_code == 200
        assert not response.get_json().get("statutory_referral")
        assert custody_cases(client) == []
        assert ipid_escalations(client)[0]["source"] == "MANUAL"

    def test_s28_citizen_escalation_is_promoted_to_a_statutory_referral(self, client):
        case_reference = registered_case(client)
        response = escalate(client, case_reference, BRIBE)
        assert response.get_json()["statutory_referral"] is True
        items = ipid_escalations(client)
        assert len(items) == 1 and items[0]["source"] == "IPID_STATUTORY_MANDATE"
        assert len(custody_cases(client)) == 1

    def test_further_statutory_text_extends_the_open_referral_rather_than_duplicating(self, client):
        case_reference = registered_case(client)
        escalate(client, case_reference, BRIBE)
        client.post(
            f"/api/v1/constable/dockets/{case_reference}/flags",
            json={"category": "OTHER", "notes": "The police officer also assaulted the complainant."},
            headers=login(client, "constable"),
        )
        # The frozen docket rejects the flag, so nothing new is created.
        assert len([i for i in ipid_escalations(client) if i["source"] == "IPID_STATUTORY_MANDATE"]) == 1
        assert len(custody_cases(client)) == 1

    def test_each_citizen_escalation_is_its_own_ticket_under_a_single_freeze(self, client):
        case_reference = registered_case(client)
        escalate(client, case_reference, BRIBE)
        escalate(client, case_reference, "The police officer also assaulted me during the visit.")
        assert len(ipid_escalations(client)) == 2
        assert len(custody_cases(client)) == 1

    def test_constable_flag_with_s28_text_triggers_referral(self, client):
        case_reference = registered_case(client)
        response = client.post(
            f"/api/v1/constable/dockets/{case_reference}/flags",
            json={"category": "OTHER", "notes": "The police officer demanded a bribe from the complainant."},
            headers=login(client, "constable"),
        )
        assert response.status_code in (200, 201)
        assert any(item["source"] == "IPID_STATUTORY_MANDATE" for item in ipid_escalations(client))

    def test_citizen_sees_the_statutory_escalation_on_their_docket(self, client):
        case_reference = registered_case(client)
        escalate(client, case_reference, BRIBE)
        listing = client.get(f"/api/v1/citizen/dockets/{case_reference}/escalations", headers=login(client, "citizen"))
        assert listing.status_code == 200
        assert listing.get_json()[0]["source"] == "IPID_STATUTORY_MANDATE"


class TestAssignmentSuspension:
    def test_implicated_assignee_is_suspended_and_reinstated_on_dismissal(self, client):
        case_reference = registered_case(client)
        assert assign(client, case_reference).status_code == 200
        escalate(client, case_reference, "The detective demanded a bribe to speed up the case.")
        ipid = login(client, "ipid")
        escalation = ipid_escalations(client)[0]
        detail = client.get(f"/api/v1/ipid/escalations/{escalation['escalation_id']}", headers=ipid).get_json()
        assert detail["suspended_officer_id"] == ROLE_TEST_IDS["detective"]
        assert assignments(client, case_reference)["current_assignment"] is None
        client.post(f"/api/v1/ipid/escalations/{escalation['escalation_id']}/review", headers=ipid)

        dismissed = client.post(
            f"/api/v1/ipid/escalations/{escalation['escalation_id']}/dismiss",
            json={"reason": "Allegation not substantiated."},
            headers=ipid,
        )
        assert dismissed.status_code == 200
        assert custody_cases(client) == []
        current = assignments(client, case_reference)["current_assignment"]
        assert current and current["officer_id"] == ROLE_TEST_IDS["detective"] and current["status"] == "ACTIVE"

    def test_the_complainant_reporting_is_never_treated_as_implicated(self, client):
        case_reference = registered_case(client)
        assert assign(client, case_reference).status_code == 200
        escalate(client, case_reference, BRIBE)
        # "police officer" is generic; the detective assignee is still the one
        # associated with the case, so suspension applies to assignees only.
        assert len(ipid_escalations(client)) == 1


class TestUpholdDeterminationAndClose:
    def _uphold(self, client, text):
        case_reference = registered_case(client)
        assign(client, case_reference)
        escalate(client, case_reference, text)
        ipid = login(client, "ipid")
        escalation_id = ipid_escalations(client)[0]["escalation_id"]
        client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=ipid)
        response = client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/uphold", json={"reason": "Corroborated by evidence."}, headers=ipid
        )
        return response, ipid

    def test_statutory_uphold_yields_tier_three_dismissal(self, client):
        response, ipid = self._uphold(client, BRIBE)
        assert response.status_code == 200, response.get_json()
        cases = client.get("/api/v1/ipid/disciplinary-cases", headers=ipid).get_json()
        assert len(cases) == 1
        assert cases[0]["misconduct_tier"] == 3
        assert cases[0]["mandatory_sanction"] == "DISMISSAL"
        assert cases[0]["determination"]

    def test_manual_uphold_yields_a_lower_tier_warning(self, client):
        response, ipid = self._uphold(client, NEUTRAL)
        assert response.status_code == 200, response.get_json()
        case = client.get("/api/v1/ipid/disciplinary-cases", headers=ipid).get_json()[0]
        assert case["misconduct_tier"] in (1, 2)
        assert case["mandatory_sanction"] in ("WARNING", "FINAL_WARNING")

    def test_closing_defaults_to_the_mandatory_sanction(self, client):
        _, ipid = self._uphold(client, BRIBE)
        case = client.get("/api/v1/ipid/disciplinary-cases", headers=ipid).get_json()[0]
        closed = client.post(f"/api/v1/ipid/disciplinary-cases/{case['disciplinary_case_id']}/close", json={}, headers=ipid)
        assert closed.status_code == 200
        body = closed.get_json()
        assert body["status"] == "CLOSED" and body["final_sanction"] == "DISMISSAL"

    def test_deviation_without_justification_is_rejected_then_accepted_with_one(self, client):
        _, ipid = self._uphold(client, BRIBE)
        case = client.get("/api/v1/ipid/disciplinary-cases", headers=ipid).get_json()[0]
        url = f"/api/v1/ipid/disciplinary-cases/{case['disciplinary_case_id']}/close"
        assert client.post(url, json={"final_sanction": "WARNING"}, headers=ipid).status_code == 400
        ok = client.post(
            url, json={"final_sanction": "SUSPENSION", "justification": "Hearing found mitigating circumstances."}, headers=ipid
        )
        assert ok.status_code == 200
        assert ok.get_json()["deviation_justification"]
        assert client.post(url, json={}, headers=ipid).status_code == 400  # already closed

    def test_close_rejects_invalid_sanction_and_non_ipid_roles(self, client):
        _, ipid = self._uphold(client, BRIBE)
        case = client.get("/api/v1/ipid/disciplinary-cases", headers=ipid).get_json()[0]
        url = f"/api/v1/ipid/disciplinary-cases/{case['disciplinary_case_id']}/close"
        assert client.post(url, json={"final_sanction": "NONSENSE", "justification": "x"}, headers=ipid).status_code == 400
        assert client.post(url, json={}, headers=login(client, "station_commander")).status_code == 403
        assert client.post("/api/v1/ipid/disciplinary-cases/missing/close", json={}, headers=ipid).status_code == 404


class TestConflictOfInterest:
    def test_officer_can_declare_and_it_blocks_assignment(self, client):
        case_reference = registered_case(client)
        declared = client.post(
            "/api/v1/conflicts/declarations",
            json={"case_reference": case_reference, "relationship_type": "FAMILY", "description": "Complainant is my cousin."},
            headers=login(client, "detective"),
        )
        assert declared.status_code == 201, declared.get_json()
        blocked = assign(client, case_reference)
        assert blocked.status_code == 400
        assert "conflict of interest" in blocked.get_json()["error"].lower()

    def test_check_endpoint_reports_conflicts_and_is_role_restricted(self, client):
        case_reference = registered_case(client)
        client.post(
            "/api/v1/conflicts/declarations",
            json={"case_reference": case_reference, "relationship_type": "FAMILY", "description": "Cousin."},
            headers=login(client, "detective"),
        )
        url = f"/api/v1/conflicts/check?case_reference={case_reference}&officer_id={ROLE_TEST_IDS['detective']}"
        result = client.get(url, headers=login(client, "station_commander"))
        assert result.status_code == 200
        assert result.get_json()["conflicted"] is True
        assert client.get(url, headers=login(client, "constable")).status_code == 403
        assert client.get("/api/v1/conflicts/check", headers=login(client, "ipid")).status_code == 400

    def test_no_conflict_allows_assignment(self, client):
        case_reference = registered_case(client)
        assert assign(client, case_reference).status_code == 200

    def test_declarations_are_listed_and_officers_see_only_their_own(self, client):
        case_reference = registered_case(client)
        client.post(
            "/api/v1/conflicts/declarations",
            json={"case_reference": case_reference, "relationship_type": "FAMILY", "description": "Cousin."},
            headers=login(client, "detective"),
        )
        mine = client.get("/api/v1/conflicts/declarations", headers=login(client, "detective")).get_json()
        others = client.get("/api/v1/conflicts/declarations", headers=login(client, "constable")).get_json()
        assert len(mine) == 1 and others == []
        assert client.get("/api/v1/conflicts/declarations", headers=login(client, "citizen")).status_code == 403

    def test_implicated_officer_cannot_be_reassigned_to_the_frozen_case(self, client):
        case_reference = registered_case(client)
        assign(client, case_reference)
        escalate(client, case_reference, "The detective demanded a bribe to speed up the case.")
        result = client.get(
            f"/api/v1/conflicts/check?case_reference={case_reference}&officer_id={ROLE_TEST_IDS['detective']}",
            headers=login(client, "ipid"),
        )
        assert result.get_json()["conflicted"] is True


class TestRegulatoryAndDecisionEndpoints:
    def test_regulatory_catalogs_are_readable_by_any_authenticated_user(self, client):
        headers = login(client, "citizen")
        for path in ("rules", "legal-references", "sanction-matrix", "misconduct-schedule", "statutory-categories", "sla-thresholds"):
            assert client.get(f"/api/v1/regulatory/{path}", headers=headers).status_code == 200, path
        assert client.get("/api/v1/regulatory/rules").status_code in (401, 422)

    def test_rules_filter_and_detail(self, client):
        headers = login(client, "ipid")
        rules = client.get("/api/v1/regulatory/rules?family=IPID.S28", headers=headers).get_json()
        assert rules and all(item["rule_code"].startswith("IPID.S28") for item in rules)
        assert client.get("/api/v1/regulatory/rules/IPID.S28.CORRUPTION", headers=headers).status_code == 200
        assert client.get("/api/v1/regulatory/rules/NOPE", headers=headers).status_code == 404

    def test_triage_preview_has_no_side_effects(self, client):
        case_reference = registered_case(client)
        result = client.post("/api/v1/decision/triage", json={"text": BRIBE}, headers=login(client, "constable"))
        assert result.status_code == 200
        assert result.get_json()["mandatory_referral"] is True
        assert custody_cases(client) == [] and ipid_escalations(client) == []
        assert client.post("/api/v1/decision/triage", json={"text": BRIBE}, headers=login(client, "citizen")).status_code == 403
        assert client.post("/api/v1/decision/triage", json=[], headers=login(client, "constable")).status_code == 400

    def test_sla_endpoint(self, client):
        case_reference = registered_case(client)
        ok = client.get(f"/api/v1/decision/dockets/{case_reference}/sla", headers=login(client, "station_commander"))
        assert ok.status_code == 200
        assert client.get("/api/v1/decision/dockets/NOPE/sla", headers=login(client, "station_commander")).status_code in (400, 404)
        assert client.get(f"/api/v1/decision/dockets/{case_reference}/sla", headers=login(client, "citizen")).status_code == 403

    def test_misconduct_tier_and_sanction_endpoints(self, client):
        ipid = login(client, "ipid")
        tier = client.post(
            "/api/v1/decision/misconduct-tier",
            json={"officer_id": ROLE_TEST_IDS["detective"], "infraction_type": "NEGLECT_OF_DUTY", "evidence_context": {"concealment": True}},
            headers=ipid,
        )
        assert tier.status_code == 200 and tier.get_json()["misconduct_tier"] == 3
        sanction = client.get(f"/api/v1/decision/officers/{ROLE_TEST_IDS['detective']}/sanction?tier=2", headers=ipid)
        assert sanction.status_code == 200 and sanction.get_json()["mandatory_sanction"] == "FINAL_WARNING"
        assert client.get(f"/api/v1/decision/officers/{ROLE_TEST_IDS['detective']}/sanction?tier=9", headers=ipid).status_code == 400
        bad = client.post("/api/v1/decision/misconduct-tier", json={"infraction_type": "BOGUS"}, headers=ipid)
        assert bad.status_code == 400
        assert client.post("/api/v1/decision/misconduct-tier", json={}, headers=login(client, "constable")).status_code == 403


class TestIpidUiSupport:
    def test_review_workspace_exposes_statutory_source_and_suspended_officer(self, client):
        case_reference = registered_case(client)
        assign(client, case_reference)
        escalate(client, case_reference, "The detective demanded a bribe to speed up the case.")
        ipid = login(client, "ipid")
        escalation_id = ipid_escalations(client)[0]["escalation_id"]
        workspace = client.get(f"/api/v1/ipid/escalations/{escalation_id}/review-workspace", headers=ipid).get_json()
        assert workspace["source"] == "IPID_STATUTORY_MANDATE"
        assert workspace["rule_code"] == "IPID.S28.CORRUPTION"
        assert workspace["statutory_basis"].startswith("IPID Act 1 of 2011")

    def test_disciplinary_detail_template_has_determination_and_close_panel(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parent.parent / "app" / "templates" / "ipid_disciplinary_case_detail.html").read_text()
        for element_id in ("disciplinaryDeterminationMeta", "disciplinaryClosePanel", "disciplinaryCloseForm", "disciplinaryJustification"):
            assert element_id in source
