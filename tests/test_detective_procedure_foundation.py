import pytest

from app.modules.procedure_engine.services import DetectiveProcedureService


@pytest.fixture()
def procedure_service(app):
    return app.extensions["detective_procedure_service"]


def test_detective_procedure_registers_source_and_rule_versioning(app, procedure_service):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Officer conduct report",
            "description": "Officer struck a citizen and the submission included a recording.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000099",
            "source_candidate_id": "IC-000099",
            "evidence": [{"evidence_id": "EVD-000099", "description": "Citizen recording"}],
        },
    )

    source = procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000099",
        source_candidate_id="IC-000099",
        evidence_ids=["EVD-000099"],
    )
    rule_v1 = procedure_service.register_rule(
        "PROCEDURE.SOURCE_CHAIN",
        title="Protected source chain",
        category="SOURCE_CONTINUITY",
        description="Detective review must preserve the citizen source record.",
        legal_basis="Protected citizen reporting remains authoritative.",
        applicability={"case_status": ["REGISTERED"]},
        required_records=["source_submission", "source_candidate"],
        version="v1",
    )
    rule_v2 = procedure_service.register_rule(
        "PROCEDURE.SOURCE_CHAIN",
        title="Protected source chain",
        category="SOURCE_CONTINUITY",
        description="Detective review must preserve the citizen source record.",
        legal_basis="Protected citizen reporting remains authoritative.",
        applicability={"case_status": ["REGISTERED"]},
        required_records=["source_submission", "source_candidate"],
        version="v2",
    )

    assert source["source_submission_id"] == "SUB-000099"
    assert rule_v1["rule_code"] == "PROCEDURE.SOURCE_CHAIN"
    assert rule_v2["version"] == "v2"
    assert procedure_service.list_rule_versions("PROCEDURE.SOURCE_CHAIN") >= {"v1", "v2"}


def test_detective_procedure_gate_blocks_forged_completion(app, procedure_service):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Protected case",
            "description": "A protected submission needs detective review.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000100",
            "source_candidate_id": "IC-000100",
            "evidence": [{"evidence_id": "EVD-000100", "description": "Authentic evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000100",
        source_candidate_id="IC-000100",
        evidence_ids=["EVD-000100"],
    )

    blocked = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333111",
        actor_role="citizen",
        action="complete_investigation",
    )

    assert blocked["allowed"] is False
    assert blocked["status"] in {"BLOCKED", "REVIEW_REQUIRED"}
    assert blocked["gate"] == "procedure"


def test_detective_procedure_gate_allows_preserved_source_review(app, procedure_service):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Preserved evidence",
            "description": "Evidence must remain read-only for detective review.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000101",
            "source_candidate_id": "IC-000101",
            "evidence": [{"evidence_id": "EVD-000101", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000101",
        source_candidate_id="IC-000101",
        evidence_ids=["EVD-000101"],
    )

    result = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="view_preserved_evidence",
    )

    assert result["allowed"] is True
    assert result["status"] == "ALLOWED"
    assert result["requirements"][0]["rule_code"] == "PROCEDURE.SOURCE_CHAIN"


def test_detective_procedure_version_lock_binds_case_to_original_source_and_rule_version(app, procedure_service):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Version lock case",
            "description": "Historical procedure interpretation must remain bound to the original version.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000201",
            "source_candidate_id": "IC-000201",
            "evidence": [{"evidence_id": "EVD-000201", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000201",
        source_candidate_id="IC-000201",
        evidence_ids=["EVD-000201"],
    )
    procedure_service.register_rule(
        "PROCEDURE.SOURCE_CHAIN",
        title="Protected source chain",
        category="SOURCE_CONTINUITY",
        description="Protected source chain v1.",
        legal_basis="Protected citizen reporting remains authoritative.",
        applicability={"case_status": ["REGISTERED"]},
        required_records=["source_submission", "source_candidate"],
        version="v1",
    )

    procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="view_preserved_evidence",
    )
    original_state = procedure_service.get_case_state(case["case_reference"])

    procedure_service.register_rule(
        "PROCEDURE.SOURCE_CHAIN",
        title="Protected source chain",
        category="SOURCE_CONTINUITY",
        description="Protected source chain v2.",
        legal_basis="Protected citizen reporting remains authoritative.",
        applicability={"case_status": ["REGISTERED"]},
        required_records=["source_submission", "source_candidate"],
        version="v2",
    )

    procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="view_preserved_evidence",
    )
    latest_state = procedure_service.get_case_state(case["case_reference"])

    assert original_state["source_version"] == latest_state["source_version"]
    assert original_state["rule_version"] == latest_state["rule_version"]
    assert original_state["ruleset_version"] == latest_state["ruleset_version"]


def test_requirement_state_tracks_not_started_to_completed_and_audits(app, procedure_service):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Requirement state case",
            "description": "Requirement lifecycle must be explicit and auditable.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000202",
            "source_candidate_id": "IC-000202",
            "evidence": [{"evidence_id": "EVD-000202", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000202",
        source_candidate_id="IC-000202",
        evidence_ids=["EVD-000202"],
    )

    requirement = procedure_service.create_requirement(
        case_reference=case["case_reference"],
        rule_code="PROCEDURE.SOURCE_CHAIN",
        rule_version="v1",
        description="Protected source chain requirement",
        required_action="view_preserved_evidence",
        required_record="source_submission",
        actor_id="2200223333115",
        actor_role="detective",
        reason="Protected source chain must be preserved before detective review.",
    )

    assert requirement["state"] == "NOT_STARTED"

    updated = procedure_service.update_requirement_state(
        requirement["requirement_id"],
        "IN_PROGRESS",
        actor_id="2200223333115",
        actor_role="detective",
        reason="Review started.",
    )
    assert updated["state"] == "IN_PROGRESS"

    completed = procedure_service.update_requirement_state(
        requirement["requirement_id"],
        "COMPLETED",
        actor_id="2200223333115",
        actor_role="detective",
        reason="Source continuity verified.",
    )
    assert completed["state"] == "COMPLETED"

    audit_events = app.extensions["audit_service"].get_for_case(case["case_reference"])
    assert any(event.get("action") == "procedure_requirement_state_changed" for event in audit_events)


def test_detective_without_assignment_cannot_mutate_procedure_state(app, procedure_service):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Unassigned detective case",
            "description": "Only the assigned detective may mutate procedure state.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000203",
            "source_candidate_id": "IC-000203",
            "evidence": [{"evidence_id": "EVD-000203", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000203",
        source_candidate_id="IC-000203",
        evidence_ids=["EVD-000203"],
    )

    result = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="start_investigation",
    )

    assert result["allowed"] is False
    assert result["status"] in {"BLOCKED", "REVIEW_REQUIRED"}
    assert "assigned" in str(result.get("message", "")).lower()


def test_detective_procedure_control_board_exposes_backend_metadata(app, procedure_service):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Control board case",
            "description": "The detective control board must show authoritative procedure metadata.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000205",
            "source_candidate_id": "IC-000205",
            "evidence": [{"evidence_id": "EVD-000205", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000205",
        source_candidate_id="IC-000205",
        evidence_ids=["EVD-000205"],
    )

    result = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="view_preserved_evidence",
    )

    assert result["profile_name"] == "DEFAULT"
    assert result["ruleset_version"] == "procedure-v1"
    assert result["current_stage"] == "CASE_REVIEW"
    assert result["procedure_status"] == "ACTIVE"
    assert result["next_permitted_action"] == "Review preserved evidence"
    assert isinstance(result["blocking_requirements"], list)
    assert result["blocking_requirements"] == []


def test_client_cannot_forge_requirement_completion_using_satisfied_payload(app, procedure_service):
    case_service = app.extensions["case_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Payload forging case",
            "description": "The backend must ignore client-supplied satisfied flags.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000204",
            "source_candidate_id": "IC-000204",
            "evidence": [{"evidence_id": "EVD-000204", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000204",
        source_candidate_id="IC-000204",
        evidence_ids=["EVD-000204"],
    )

    requirement = procedure_service.create_requirement(
        case_reference=case["case_reference"],
        rule_code="PROCEDURE.SOURCE_CHAIN",
        rule_version="v1",
        description="Protected source chain requirement",
        required_action="view_preserved_evidence",
        required_record="source_submission",
        actor_id="2200223333115",
        actor_role="detective",
        reason="Protected source chain must be preserved before detective review.",
    )

    forged = procedure_service.update_requirement_state(
        requirement["requirement_id"],
        None,
        actor_id="2200223333115",
        actor_role="detective",
        reason="Client tried to forge completion.",
        payload={"satisfied": True},
    )

    assert forged["state"] == "NOT_STARTED"
    assert forged["satisfied"] is False


def test_start_investigation_is_blocked_until_case_facts_verification_for_registered_cases(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Case facts gate case",
            "description": "The investigation cannot start until the detective verifies the case facts.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000206",
            "source_candidate_id": "IC-000206",
            "evidence": [{"evidence_id": "EVD-000206", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000206",
        source_candidate_id="IC-000206",
        evidence_ids=["EVD-000206"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    result = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="start_investigation",
    )

    assert result["allowed"] is False
    assert result["status"] in {"BLOCKED", "REVIEW_REQUIRED"}
    assert result["next_permitted_action"] == "Verify case facts"
    assert result["current_stage"] == "CASE_FACTS_VERIFICATION"


def test_start_investigation_is_blocked_until_case_facts_verification(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Investigation start remains blocked before case facts",
            "description": "The investigation action must be gated until the detective verifies the incident facts.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000211",
            "source_candidate_id": "IC-000211",
            "evidence": [{"evidence_id": "EVD-000211", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000211",
        source_candidate_id="IC-000211",
        evidence_ids=["EVD-000211"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    result = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="start_investigation",
    )

    assert result["allowed"] is False
    assert result["status"] in {"BLOCKED", "REVIEW_REQUIRED"}
    assert result["next_permitted_action"] == "Verify case facts"


def test_detective_case_facts_verification_allows_missing_incident_time(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]

    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Missing incident time case",
            "description": "A case with a preserved incident date but no source time must still pass Case Facts verification when the detective leaves time blank or unknown.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000215",
            "source_candidate_id": "IC-000215",
            "evidence": [{"evidence_id": "EVD-000215", "description": "Original evidence"}],
            "incident_date": "2026-09-20",
            "location": "Main St",
            "people_involved": ["Victim", "Suspect"],
            "witnesses": ["Witness A"],
            "harm_types": ["assault"],
            "injury_types": ["bruising"],
            "police_involvement": False,
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000215",
        source_candidate_id="IC-000215",
        evidence_ids=["EVD-000215"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    result = procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-09-20",
                "incident_time": "",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [],
        },
    )

    assert result["verified"] is True
    assert result["record"]["facts"]["incident_time"] in {None, "", "UNKNOWN", "NOT_ESTABLISHED"}


def test_detective_case_facts_verification_persists_deterministic_field_comparisons(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]

    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Deterministic comparison case",
            "description": "The backend must compare each detective-entered fact against the protected source and persist a deterministic field comparison result.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000213",
            "source_candidate_id": "IC-000213",
            "evidence": [{"evidence_id": "EVD-000213", "description": "Original evidence"}],
            "incident_date": "2026-04-10",
            "incident_time": None,
            "location": "Main St",
            "people_involved": ["Victim", "Suspect"],
            "witnesses": ["Witness A"],
            "harm_types": ["assault"],
            "injury_types": ["bruising"],
            "police_involvement": False,
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000213",
        source_candidate_id="IC-000213",
        evidence_ids=["EVD-000213"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    result = procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-04-11",
                "incident_time": "",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [{
                "field": "incident_date",
                "original_value": "2026-04-10",
                "observed_value": "2026-04-11",
                "basis": "The detective documented the later date after a clerical correction.",
                "status": "ADDRESSED",
            }],
        },
    )

    comparison = result["record"]["comparison"]
    assert comparison["incident_date"]["comparison_status"] == "DISCREPANCY"
    assert comparison["incident_date"]["status"] == "DISCREPANCY"
    assert comparison["incident_time"]["comparison_status"] == "NOT_ESTABLISHED"
    assert result["record"]["comparison_results"][0]["field"] in {"incident_date", "incident_time", "location", "people_involved", "witnesses", "harm_types", "injury_types", "police_involvement"}
    assert result["verified"] is True


def test_detective_docket_reloads_persisted_case_facts_verification(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]
    investigation_service = app.extensions["investigation_service"]

    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Persisted case facts reload case",
            "description": "The detective docket must include the saved comparison results after a fresh reload.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000216",
            "source_candidate_id": "IC-000216",
            "evidence": [{"evidence_id": "EVD-000216", "description": "Original evidence"}],
            "incident_date": "2026-04-10",
            "incident_time": None,
            "location": "Main St",
            "people_involved": ["Victim", "Suspect"],
            "witnesses": ["Witness A"],
            "harm_types": ["assault"],
            "injury_types": ["bruising"],
            "police_involvement": False,
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000216",
        source_candidate_id="IC-000216",
        evidence_ids=["EVD-000216"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-04-10",
                "incident_time": "",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [],
        },
    )

    docket = investigation_service.get_docket_for_detective(case["case_reference"], "2200223333115")

    assert docket.get("case_facts_verification") is not None
    assert docket["case_facts_verification"]["verified"] is True
    assert docket["case_facts_verification"]["comparison_results"]
    assert any(item.get("field") == "incident_time" for item in docket["case_facts_verification"]["comparison_results"])


def test_detective_case_facts_ignores_boolean_people_flags_when_source_has_no_names(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]

    case = case_service.create_case(
        "2200223333111",
        {
            "title": "People field mapping case",
            "description": "The protected source records only that other people were involved and a count, not the exact names.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000217",
            "source_candidate_id": "IC-000217",
            "evidence": [{"evidence_id": "EVD-000217", "description": "Original evidence"}],
            "incident_date": "2026-09-20",
            "location": "Main St",
            "other_people_involved": "Yes",
            "people_count": "3-5",
            "harm_types": ["assault"],
            "injury_types": ["bruising"],
            "police_involvement": True,
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000217",
        source_candidate_id="IC-000217",
        evidence_ids=["EVD-000217"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    result = procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-09-20",
                "incident_time": "",
                "location": "Main St",
                "people_involved": ["Male driver", "Police official 1", "Police official 2"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": True,
            },
            "discrepancies": [],
        },
    )

    assert result["verified"] is True
    assert result["record"]["comparison"]["incident_time"]["comparison_status"] == "NOT_ESTABLISHED"
    assert result["record"]["comparison"]["people_involved"]["comparison_status"] == "NOT_ESTABLISHED"
    assert result["record"]["comparison"]["people_involved"]["status"] == "NOT_ESTABLISHED"


def test_detective_case_facts_verification_is_idempotent_after_success(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]

    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Idempotent verification case",
            "description": "A successful verification should not create a second verification record or reopen the gate.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000218",
            "source_candidate_id": "IC-000218",
            "evidence": [{"evidence_id": "EVD-000218", "description": "Original evidence"}],
            "incident_date": "2026-09-20",
            "location": "Main St",
            "people_involved": ["Victim", "Suspect"],
            "witnesses": ["Witness A"],
            "harm_types": ["assault"],
            "injury_types": ["bruising"],
            "police_involvement": False,
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000218",
        source_candidate_id="IC-000218",
        evidence_ids=["EVD-000218"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    first = procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-09-20",
                "incident_time": "",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [],
        },
    )
    before_count = len(procedure_service.state_repository.list_for_case(case["case_reference"]))

    second = procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-09-20",
                "incident_time": "",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [],
        },
    )

    after_count = len(procedure_service.state_repository.list_for_case(case["case_reference"]))
    assert first["verified"] is True
    assert second["verified"] is True
    assert second.get("idempotent") is True
    assert after_count == before_count
    assert second["record"]["status"] == "VERIFIED"


def test_detective_case_facts_verification_allows_addressed_discrepancies(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]

    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Addressed discrepancy case",
            "description": "A discrepancy must remain blocked until the detective explicitly addresses the factual inconsistency.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000214",
            "source_candidate_id": "IC-000214",
            "evidence": [{"evidence_id": "EVD-000214", "description": "Original evidence"}],
            "incident_date": "2026-03-10",
            "incident_time": "18:30",
            "location": "Main St",
            "people_involved": ["Victim", "Suspect"],
            "witnesses": ["Witness A"],
            "harm_types": ["assault"],
            "injury_types": ["bruising"],
            "police_involvement": False,
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000214",
        source_candidate_id="IC-000214",
        evidence_ids=["EVD-000214"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    result = procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-03-05",
                "incident_time": "18:30",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [{
                "field": "incident_date",
                "original_value": "2026-03-10",
                "observed_value": "2026-03-05",
                "basis": "Witness statement and source ledger reconcile to 2026-03-10.",
                "status": "ADDRESSED",
            }],
        },
    )

    assert result["verified"] is True
    assert result["discrepancies"][0]["status"] in {"ADDRESSED", "RESOLVED"}


def test_detective_case_facts_verification_becomes_active_stage_after_investigation_opens(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]
    investigation_service = app.extensions["investigation_service"]

    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Open investigation facts stage case",
            "description": "Case facts verification must be completed before an investigation can start.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000212",
            "source_candidate_id": "IC-000212",
            "evidence": [{"evidence_id": "EVD-000212", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000212",
        source_candidate_id="IC-000212",
        evidence_ids=["EVD-000212"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    blocked = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="start_investigation",
    )
    assert blocked["allowed"] is False
    assert blocked["status"] in {"BLOCKED", "REVIEW_REQUIRED"}
    assert "required records are missing" in (blocked["blocking_reason"] or "").lower()

    procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-01-15",
                "incident_time": "18:30",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [],
        },
    )

    investigation = investigation_service.create_investigation(
        case["case_reference"],
        "2200223333115",
        {"notes": "Investigation opened from the browser workflow."},
    )
    assert investigation["status"] == "OPEN"

    result = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="view_preserved_evidence",
    )

    assert result["current_stage"] == "INVESTIGATION_OPEN"
    assert result["next_permitted_action"] == "Complete investigation"
    assert result["current_action"] == "complete_investigation"
    assert result["allowed"] is True

    completion = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="complete_investigation",
    )
    assert completion["allowed"] is False
    assert completion["status"] in {"BLOCKED", "REVIEW_REQUIRED"}


def test_detective_procedure_advances_to_findings_ready_after_all_required_actions(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]
    investigation_service = app.extensions["investigation_service"]

    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Findings gate case",
            "description": "Once all six required investigative actions are complete, the detective should advance to the findings gate.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000214",
            "source_candidate_id": "IC-000214",
            "evidence": [{"evidence_id": "EVD-000214", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000214",
        source_candidate_id="IC-000214",
        evidence_ids=["EVD-000214"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])
    procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-01-15",
                "incident_time": "18:30",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [],
        },
    )

    investigation = investigation_service.create_investigation(
        case["case_reference"],
        "2200223333115",
        {"notes": "Investigation opened from the browser workflow."},
    )
    for action_type in [
        "INTERVIEW",
        "EVIDENCE_REVIEW",
        "EVIDENCE_COLLECTION",
        "RECORD_REQUEST",
        "WITNESS_CONTACT",
        "SCENE_REVIEW",
    ]:
        investigation_service.create_action(
            investigation["investigation_id"],
            "2200223333115",
            {
                "action_type": action_type,
                "purpose": f"Required step: {action_type}",
                "description": f"Completed the {action_type.lower().replace('_', ' ')} step.",
                "result": "Recorded.",
            },
        )

    result = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="view_preserved_evidence",
    )

    assert result["current_stage"] == "FINDINGS_READY"
    assert result["allowed"] is True
    assert result["next_permitted_action"] == "Document finding"
    assert result["current_action"] == "record_finding"


def test_detective_case_facts_verification_allows_investigation_start_when_complete(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Verified facts case",
            "description": "Once the detective verifies the basic incident facts, investigation may begin.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000206",
            "source_candidate_id": "IC-000206",
            "evidence": [{"evidence_id": "EVD-000206", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000206",
        source_candidate_id="IC-000206",
        evidence_ids=["EVD-000206"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])
    procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-01-15",
                "incident_time": "18:30",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [],
        },
    )

    result = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="start_investigation",
    )

    assert result["allowed"] is True
    assert result["status"] in {"ALLOWED", "ACTIVE"}
    assert result["next_permitted_action"] == "Start investigation"


def test_start_investigation_reconciles_procedure_state_with_open_investigation(app, procedure_service):
    case_service = app.extensions["case_service"]
    investigation_service = app.extensions["investigation_service"]
    assignment_service = app.extensions["assignment_service"]

    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Open investigation state case",
            "description": "Procedure state must reconcile to the active investigation lifecycle.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000208",
            "source_candidate_id": "IC-000208",
            "evidence": [{"evidence_id": "EVD-000208", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000208",
        source_candidate_id="IC-000208",
        evidence_ids=["EVD-000208"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    before = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="view_preserved_evidence",
    )
    assert before["current_stage"] == "CASE_REVIEW"
    assert before["next_permitted_action"] == "Review preserved evidence"

    procedure_service.record_case_facts_verification(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        payload={
            "facts": {
                "incident_date": "2026-01-15",
                "incident_time": "18:30",
                "location": "Main St",
                "people_involved": ["Victim", "Suspect"],
                "witnesses": ["Witness A"],
                "harm_types": ["assault"],
                "injury_types": ["bruising"],
                "police_involvement": False,
            },
            "discrepancies": [],
        },
    )

    investigation = investigation_service.create_investigation(
        case["case_reference"],
        "2200223333115",
        {"notes": "Investigation opened from the browser workflow."},
    )
    assert investigation["status"] == "OPEN"

    after_start = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="start_investigation",
    )
    assert after_start["current_stage"] == "INVESTIGATION_OPEN"
    assert after_start["status"] in {"ALLOWED", "ACTIVE"}
    assert after_start["next_permitted_action"] == "Complete investigation"

    refreshed = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="view_preserved_evidence",
    )
    assert refreshed["current_stage"] == "INVESTIGATION_OPEN"
    assert refreshed["next_permitted_action"] == "Complete investigation"
    assert refreshed["current_action"] == "complete_investigation"


def test_detective_procedure_blocks_completion_before_backend_gate_permits_it(app, procedure_service):
    case_service = app.extensions["case_service"]
    assignment_service = app.extensions["assignment_service"]
    case = case_service.create_case(
        "2200223333111",
        {
            "title": "Completion gate case",
            "description": "Completion must remain blocked until the procedure gate allows it.",
            "status": "REGISTERED",
            "source_submission_id": "SUB-000208",
            "source_candidate_id": "IC-000208",
            "evidence": [{"evidence_id": "EVD-000208", "description": "Original evidence"}],
        },
    )

    procedure_service.register_case_source(
        case["case_reference"],
        source_submission_id="SUB-000208",
        source_candidate_id="IC-000208",
        evidence_ids=["EVD-000208"],
    )
    assignment_service.ensure_initial_detective_assignment(case["case_reference"])

    result = procedure_service.evaluate_case(
        case["case_reference"],
        actor_id="2200223333115",
        actor_role="detective",
        action="complete_investigation",
    )

    assert result["allowed"] is False
    assert result["status"] in {"BLOCKED", "REVIEW_REQUIRED"}
    assert "complete" in str(result.get("message", "")).lower() or "procedure" in str(result.get("message", "")).lower()
