import pytest

VALID_CITIZEN_ID = "2200223333111"
VALID_CONSTABLE_ID = "2200223333114"
VALID_DETECTIVE_ID = "2200223333115"


def login(app_client, test_id):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": test_id},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def create_and_submit_docket(app_client, token, title, description="This is a sufficiently detailed account of the incident for investigation."):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, title, description)
    case_reference = case["case_reference"]

    statement_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {token}"},
        json={"statement_text": "This is the statement I am submitting for detective review."},
    )
    assert statement_response.status_code == 201

    submit_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert submit_response.status_code == 200
    return case_reference


def register_case(app_client, citizen_token, constable_token, title="Registered case"):
    case_reference = create_and_submit_docket(app_client, citizen_token, title)

    interview_response = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/interview",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"status": "STARTED"},
    )
    assert interview_response.status_code == 201
    interview_id = interview_response.get_json()["interview_id"]

    app_client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "recording_type": "citizen_recording",
            "storage_reference": "citizen-register.wav",
            "filename": "citizen-register.wav",
        },
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={
            "recording_type": "constable_recording",
            "storage_reference": "constable-register.wav",
            "filename": "constable-register.wav",
        },
    )

    register = app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/register",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert register.status_code == 200

    from tests.conftest import assign_detective_to_case

    assign_detective_to_case(app_client, case_reference, VALID_DETECTIVE_ID)
    return case_reference


@pytest.fixture()
def citizen_token(app_client):
    return login(app_client, VALID_CITIZEN_ID)


@pytest.fixture()
def constable_token(app_client):
    return login(app_client, VALID_CONSTABLE_ID)


@pytest.fixture()
def detective_token(app_client):
    return login(app_client, VALID_DETECTIVE_ID)


def _service(app_client):
    return app_client.application.extensions["investigation_service"]


def test_investigation_creation_rejects_frozen_case(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Frozen investigation gate")
    freeze_service = app_client.application.extensions["freeze_service"]
    freeze_service.freeze_case(case_reference, VALID_CONSTABLE_ID, "constable", reason="frozen for hardening", source="MANUAL")

    with pytest.raises(ValueError, match="frozen|restricted"):
        _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Blocked by freeze."})


def test_finding_requires_evidence_reference_when_case_has_evidence(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Evidence linked findings case")
    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_case(case_reference)
    case.setdefault("evidence", []).append({
        "evidence_id": "EV-1",
        "evidence_type": "PHOTO",
        "description": "Incident photo.",
        "source": "citizen",
        "status": "SUBMITTED",
    })
    case_service.update_case(case)

    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]

    with pytest.raises(ValueError, match="evidence|link"):
        _service(app_client).create_finding(
            investigation_id,
            VALID_DETECTIVE_ID,
            {"finding_type": "VALID", "notes": "I think this is valid.", "evidence_ids": []},
        )


def test_completion_requires_a_real_finding_and_final_reasoning(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Completion control case")
    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]

    with pytest.raises(ValueError, match="finding|final reasoning|reasoning"):
        _service(app_client).complete_investigation(
            investigation_id,
            VALID_DETECTIVE_ID,
            {"outcome": "VALID", "final_notes": ""},
        )


def test_completion_succeeds_when_case_evidence_is_linked_to_a_finding(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Evidence linkage completion case")
    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_case(case_reference)
    case.setdefault("evidence", []).append({
        "evidence_id": "EV-2",
        "evidence_type": "STATEMENT",
        "description": "Supporting witness material.",
        "source": "detective",
        "status": "SUBMITTED",
    })
    case_service.update_case(case)

    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]
    _service(app_client).create_finding(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"finding_type": "VALID", "notes": "Finding is recorded.", "evidence_ids": ["EV-2"]},
    )

    result = _service(app_client).complete_investigation(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"outcome": "VALID", "final_notes": "The evidence is sufficient."},
    )

    assert result["status"] == "COMPLETED"
    assert result["outcome"] == "VALID"


def test_completion_rejects_guilt_or_innocence_outcomes(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Blocked guilt-bearing conclusion")
    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_case(case_reference)
    case.setdefault("evidence", []).append({
        "evidence_id": "EV-REJECT-1",
        "evidence_type": "STATEMENT",
        "description": "Case evidence for conclusion gate check.",
        "source": "detective",
        "status": "SUBMITTED",
    })
    case_service.update_case(case)

    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]
    _service(app_client).create_finding(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"finding_type": "VALID", "notes": "Evidence supports a valid finding.", "evidence_ids": ["EV-REJECT-1"]},
    )

    for outcome in ("GUILTY", "NOT_GUILTY"):
        with pytest.raises(ValueError, match="GUILTY|NOT_GUILTY|investigative conclusion"):
            _service(app_client).complete_investigation(
                investigation_id,
                VALID_DETECTIVE_ID,
                {"outcome": outcome, "final_notes": "This must be rejected."},
            )


def test_finding_creation_rejects_guilt_or_innocence_types(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Blocked guilt-bearing finding")
    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]

    for finding_type in ("GUILTY", "NOT_GUILTY"):
        with pytest.raises(ValueError, match="GUILTY|NOT_GUILTY|finding type"):
            _service(app_client).create_finding(
                investigation_id,
                VALID_DETECTIVE_ID,
                {"finding_type": finding_type, "notes": "This finding should be rejected."},
            )


def test_direct_api_bypass_is_blocked_for_frozen_case(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "API bypass case")
    freeze_service = app_client.application.extensions["freeze_service"]
    freeze_service.freeze_case(case_reference, VALID_CONSTABLE_ID, "constable", reason="freeze for bypass test", source="MANUAL")

    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Direct bypass attempt."},
    )
    assert response.status_code == 400
    assert "frozen" in response.get_json()["error"].lower()


def test_blocked_action_does_not_mutate_investigation_state(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Mutation guard case")
    before = _service(app_client).repository.list_for_case(case_reference)

    freeze_service = app_client.application.extensions["freeze_service"]
    freeze_service.freeze_case(case_reference, VALID_CONSTABLE_ID, "constable", reason="freeze before mutation", source="MANUAL")

    with pytest.raises(ValueError):
        _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "This must be blocked."})

    after = _service(app_client).repository.list_for_case(case_reference)
    assert len(after) == len(before)


def test_successful_investigation_actions_are_audited(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Audit case")
    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]

    _service(app_client).create_finding(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"finding_type": "VALID", "notes": "Evidence supports a valid finding.", "evidence_ids": []},
    )

    audit = app_client.application.extensions["audit_service"].get_for_case(case_reference)
    action_names = {item.get("action") for item in audit}
    assert "investigation_created" in action_names or "investigation_start_attempted" in action_names
    assert "detective_finding_created" in action_names or "finding_created" in action_names


def test_phase5c_finding_requires_explicit_case_basis_and_preserves_material(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Phase 5C basis case")
    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_case(case_reference)
    case.setdefault("evidence", []).append({
        "evidence_id": "EV-CASE-1",
        "evidence_type": "PHOTO",
        "description": "Key incident photo.",
        "source": "citizen",
        "status": "SUBMITTED",
    })
    case_service.update_case(case)

    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]

    claim_repository = app_client.application.extensions["claim_repository"]
    submission_id = case.get("source_submission_id") or "SUB-CASE-1"
    claim = claim_repository.create({
        "claim_id": "CLM-CASE-1",
        "assertion_id": "AST-CASE-1",
        "submission_id": submission_id,
        "citizen_id": VALID_CITIZEN_ID,
        "source_actor_id": VALID_CITIZEN_ID,
        "source_actor_role": "citizen",
        "provenance": "CITIZEN_ASSERTED",
        "claim_type": "asserted_fact",
        "subject": "incident",
        "predicate": "occurred",
        "object_value": "at the location",
        "created_at": "2026-01-01T00:00:00+00:00",
        "source": "assertion_extraction",
        "relation_type": "SAME_EVENT",
        "source_assertion_ids": ["AST-CASE-1"],
        "assessment_state": "CITIZEN_ASSERTED",
        "claim_metadata": {},
    })

    statement_id = case["statements"][0]["statement_id"] if case.get("statements") else "ST-CASE-1"
    create_response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/findings",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "finding_type": "VALID",
            "notes": "The evidence is sufficient; the case should remain registered.",
            "evidence_ids": ["EV-CASE-1"],
            "claim_ids": [claim["claim_id"]],
            "supporting_material": [{"kind": "evidence", "id": "EV-CASE-1", "relationship": "SUPPORTS"}],
            "contradicting_material": [{"kind": "statement", "id": str(statement_id), "relationship": "CONTRADICTS"}],
        },
    )
    assert create_response.status_code == 201, create_response.get_data(as_text=True)
    payload = create_response.get_json()
    assert payload["evidence_ids"] == ["EV-CASE-1"]
    assert payload["claim_ids"] == [claim["claim_id"]]
    assert payload["supporting_material"][0]["relationship"] == "SUPPORTS"
    assert payload["contradicting_material"][0]["relationship"] == "CONTRADICTS"

    stored_case = case_service.get_case(case_reference)
    assert stored_case["status"] == "REGISTERED"


def test_phase5c_finding_versioning_preserves_guardrails(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Phase 5C versioning case")
    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]

    created = _service(app_client).create_finding(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "finding_type": "VALID",
            "notes": "Initial conclusion based on visible evidence.",
            "evidence_ids": [],
            "reasoning": "Initial reasoning text.",
        },
    )
    assert created["version"] == 1

    with pytest.raises(ValueError, match="immutable|overwrite|version"):
        _service(app_client).finding_repository.update(created["finding_id"], {"notes": "Silent overwrite"})

    with pytest.raises(ValueError, match="amend|version|immutable"):
        _service(app_client).amend_finding(investigation_id, VALID_DETECTIVE_ID, created["finding_id"], {"notes": "Amended version"})


def test_post_investigation_gate_keeps_review_required_out_of_allowed_actions(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Post-investigation review gate case")
    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]
    _service(app_client).complete_investigation(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"outcome": "REVIEW_REQUIRED", "final_notes": "The matter requires additional review before any procedural action."},
    )

    decision = app_client.application.extensions["decision_engine"].evaluate_post_investigation_action(case_reference)
    assert decision["status"] == "REVIEW_REQUIRED"
    assert decision["allowed"] is False
    assert decision["action"] == "REVIEW_REQUIRED"


def test_post_investigation_gate_allows_statutory_referral_when_rule_trigger_exists(app_client, citizen_token, constable_token, detective_token):
    case_reference = register_case(app_client, citizen_token, constable_token, "Post-investigation statutory gate case")
    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_case(case_reference)
    case["description"] = "The officer demanded a bribe from the complainant during the stop."
    case_service.update_case(case)

    investigation_id = _service(app_client).create_investigation(case_reference, VALID_DETECTIVE_ID, {"notes": "Initial investigation opened."})["investigation_id"]
    _service(app_client).create_finding(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"finding_type": "VALID", "notes": "The allegation is supported by the available record.", "evidence_ids": []},
    )
    _service(app_client).complete_investigation(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"outcome": "VALID", "final_notes": "The allegation is corroborated and the record is complete."},
    )

    decision = app_client.application.extensions["decision_engine"].evaluate_post_investigation_action(case_reference)
    assert decision["status"] == "ALLOWED"
    assert decision["allowed"] is True
    assert decision["action"] == "IPID_STATUTORY_REFERRAL"
    assert decision["rule_codes"]
