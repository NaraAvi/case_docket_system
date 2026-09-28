"""SQLAlchemy models for the PDAS Case Docket System."""

from datetime import datetime, timezone

from app.extensions import db


def _utc_now():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.String(13), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    access_state = db.Column(db.String(20), default="ACTIVE", nullable=False)
    source = db.Column(db.String(100), default="development_test")
    created_at = db.Column(db.DateTime, default=_utc_now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "test_id": self.test_id,
            "full_name": self.full_name,
            "role": self.role,
            "active": self.active,
            "access_state": self.access_state,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Submission(db.Model):
    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    citizen_id = db.Column(db.String(13), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=False)
    incident_date = db.Column(db.String(50))
    location = db.Column(db.String(500))
    status = db.Column(db.String(50), default="RECEIVED", nullable=False, index=True)
    original_content = db.Column(db.JSON, default=dict, nullable=False)
    provenance = db.Column(db.JSON, default=dict, nullable=False)
    receipt_timestamp = db.Column(db.String(50), nullable=False)
    event_history = db.Column(db.JSON, default=list, nullable=False)
    created_at = db.Column(db.DateTime, default=_utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utc_now, onupdate=_utc_now)


class SubmissionEvent(db.Model):
    __tablename__ = "submission_events"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    submission_id = db.Column(db.String(50), nullable=False, index=True)
    event_type = db.Column(db.String(100), nullable=False)
    actor_id = db.Column(db.String(13), nullable=False)
    actor_role = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)
    details = db.Column(db.JSON, default=dict, nullable=False)
    created_at = db.Column(db.DateTime, default=_utc_now, nullable=False)


class RuleEvaluation(db.Model):
    __tablename__ = "rule_evaluations"

    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    rule_code = db.Column(db.String(150), nullable=False, index=True)
    rule_version = db.Column(db.String(50), nullable=True)
    subject = db.Column(db.String(150), nullable=False, index=True)
    result = db.Column(db.String(80), nullable=False, index=True)
    reason = db.Column(db.Text, nullable=False)
    inputs = db.Column(db.JSON, default=dict, nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)
    source_context = db.Column(db.String(200), nullable=True)
    related_submission_id = db.Column(db.String(50), nullable=True, index=True)
    related_candidate_id = db.Column(db.String(50), nullable=True, index=True)
    related_case_reference = db.Column(db.String(50), nullable=True, index=True)
    legal_basis = db.Column(db.Text, nullable=True)
    metadata_json = db.Column("metadata", db.JSON, default=dict, nullable=False)
    created_at = db.Column(db.DateTime, default=_utc_now, nullable=False)


class ControlEvaluation(db.Model):
    __tablename__ = "control_evaluations"

    id = db.Column(db.Integer, primary_key=True)
    control_evaluation_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    subject_action = db.Column(db.String(200), nullable=False, index=True)
    related_rule_evaluation_ids = db.Column(db.JSON, default=list, nullable=False)
    result = db.Column(db.String(80), nullable=False, index=True)
    reason = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)
    actor_id = db.Column(db.String(100), nullable=True, index=True)
    actor_role = db.Column(db.String(50), nullable=True)
    source_submission_id = db.Column(db.String(50), nullable=True, index=True)
    source_candidate_id = db.Column(db.String(50), nullable=True, index=True)
    source_case_reference = db.Column(db.String(50), nullable=True, index=True)
    resulting_transition = db.Column(db.String(200), nullable=True)
    metadata_json = db.Column("metadata", db.JSON, default=dict, nullable=False)
    created_at = db.Column(db.DateTime, default=_utc_now, nullable=False)


class SubmissionEvidence(db.Model):
    __tablename__ = "submission_evidence"

    id = db.Column(db.Integer, primary_key=True)
    evidence_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    submission_id = db.Column(db.String(50), nullable=False, index=True)
    citizen_id = db.Column(db.String(13), nullable=False, index=True)
    source_actor_id = db.Column(db.String(13), nullable=False, index=True)
    source_actor_role = db.Column(db.String(50), nullable=False, default="citizen")
    evidence_type = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(200), nullable=True)
    content_type = db.Column(db.String(100), nullable=True)
    storage_reference = db.Column(db.String(200), nullable=False, index=True)
    sha256_hash = db.Column(db.String(200), nullable=False, index=True)
    integrity_status = db.Column(db.String(50), nullable=False, default="VERIFIED", index=True)
    source = db.Column(db.String(100), nullable=False, default="citizen_submission")
    original_reference = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.String(50), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    handling_history = db.Column(db.JSON, default=list, nullable=False)
    metadata_json = db.Column("metadata", db.JSON, default=dict, nullable=False)


class SubmissionCorrection(db.Model):
    __tablename__ = "submission_corrections"

    id = db.Column(db.Integer, primary_key=True)
    correction_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    submission_id = db.Column(db.String(50), nullable=False, index=True)
    citizen_id = db.Column(db.String(13), nullable=False, index=True)
    original_assertion_id = db.Column(db.String(80), nullable=False, index=True)
    corrected_assertion_id = db.Column(db.String(80), nullable=False, index=True)
    relationship_type = db.Column(db.String(50), nullable=False, default="correction_for", index=True)
    reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.String(50), nullable=False)
    metadata_json = db.Column("metadata", db.JSON, default=dict, nullable=False)


class WithdrawalRequest(db.Model):
    __tablename__ = "withdrawal_requests"

    id = db.Column(db.Integer, primary_key=True)
    withdrawal_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    submission_id = db.Column(db.String(50), nullable=False, index=True)
    citizen_id = db.Column(db.String(13), nullable=False, index=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="REQUESTED", index=True)
    control_evaluation_id = db.Column(db.String(80), nullable=True, index=True)
    created_at = db.Column(db.String(50), nullable=False)
    metadata_json = db.Column("metadata", db.JSON, default=dict, nullable=False)


class Assertion(db.Model):
    __tablename__ = "assertions"

    id = db.Column(db.Integer, primary_key=True)
    assertion_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    submission_id = db.Column(db.String(50), nullable=False, index=True)
    citizen_id = db.Column(db.String(13), nullable=False, index=True)
    source_actor_id = db.Column(db.String(13), nullable=False, index=True)
    source_actor_role = db.Column(db.String(50), nullable=False, default="citizen")
    provenance = db.Column(db.String(50), nullable=False, default="CITIZEN_ASSERTED", index=True)
    assertion_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.String(50), nullable=False)
    source = db.Column(db.String(100), nullable=False, default="citizen_submission")
    version = db.Column(db.Integer, nullable=False, default=1)
    assertion_metadata = db.Column(db.JSON, default=dict, nullable=False)


class Claim(db.Model):
    __tablename__ = "claims"

    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    assertion_id = db.Column(db.String(50), nullable=False, index=True)
    submission_id = db.Column(db.String(50), nullable=False, index=True)
    citizen_id = db.Column(db.String(13), nullable=False, index=True)
    source_actor_id = db.Column(db.String(13), nullable=False, index=True)
    source_actor_role = db.Column(db.String(50), nullable=False, default="citizen")
    provenance = db.Column(db.String(50), nullable=False, default="CITIZEN_ASSERTED", index=True)
    claim_type = db.Column(db.String(80), nullable=False, default="asserted_fact")
    subject = db.Column(db.String(200), nullable=True)
    predicate = db.Column(db.String(200), nullable=True)
    object_value = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.String(50), nullable=False)
    source = db.Column(db.String(100), nullable=False, default="assertion_extraction")
    relation_type = db.Column(db.String(50), nullable=True)
    source_assertion_ids = db.Column(db.JSON, default=list, nullable=False)
    assessment_state = db.Column(db.String(50), nullable=False, default="CITIZEN_ASSERTED")
    claim_metadata = db.Column(db.JSON, default=dict, nullable=False)


class IncidentCandidate(db.Model):
    __tablename__ = "incident_candidates"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    status = db.Column(db.String(50), nullable=False, default="PROVISIONAL", index=True)
    provenance = db.Column(db.String(50), nullable=False, default="SYSTEM_DERIVED", index=True)
    derivation_rule = db.Column(db.String(200), nullable=False, default="shared_claim_context")
    explanation = db.Column(db.Text, nullable=False)
    source_submission_ids = db.Column(db.JSON, default=list, nullable=False)
    source_assertion_ids = db.Column(db.JSON, default=list, nullable=False)
    source_claim_ids = db.Column(db.JSON, default=list, nullable=False)
    deterministic_basis = db.Column(db.JSON, default=dict, nullable=False)
    created_at = db.Column(db.String(50), nullable=False)
    created_by = db.Column(db.String(50), nullable=True)
    source_actor_id = db.Column(db.String(13), nullable=True, index=True)
    source_actor_role = db.Column(db.String(50), nullable=False, default="system")


class Relationship(db.Model):
    __tablename__ = "relationships"

    id = db.Column(db.Integer, primary_key=True)
    relationship_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    candidate_id = db.Column(db.String(50), nullable=True, index=True)
    source_submission_id = db.Column(db.String(50), nullable=False, index=True)
    related_submission_id = db.Column(db.String(50), nullable=False, index=True)
    relationship_type = db.Column(db.String(80), nullable=False, index=True)
    status = db.Column(db.String(50), nullable=False, default="PROVISIONAL", index=True)
    provenance = db.Column(db.String(50), nullable=False, default="SYSTEM_DERIVED", index=True)
    explanation = db.Column(db.Text, nullable=False)
    source_basis = db.Column(db.JSON, default=dict, nullable=False)
    source_claim_ids = db.Column(db.JSON, default=list, nullable=False)
    source_assertion_ids = db.Column(db.JSON, default=list, nullable=False)
    created_at = db.Column(db.String(50), nullable=False)
    rule_name = db.Column(db.String(200), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)


class CaseDocket(db.Model):
    __tablename__ = "case_dockets"

    id = db.Column(db.Integer, primary_key=True)
    case_reference = db.Column(db.String(50), unique=True, nullable=False, index=True)
    citizen_id = db.Column(db.String(13), nullable=False, index=True)
    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default="DRAFT", nullable=False, index=True)
    incident_date = db.Column(db.String(50))
    location = db.Column(db.String(500))
    source_submission_id = db.Column(db.String(50), nullable=True, index=True)
    source_candidate_id = db.Column(db.String(50), nullable=True, index=True)
    case_origin = db.Column(db.String(50), nullable=True, default="manual")
    gate_decision = db.Column(db.String(50), nullable=True, default=None)
    interview_id = db.Column(db.String(100))
    registered_at = db.Column(db.String(50))
    submitted_at = db.Column(db.String(50))
    created_at = db.Column(db.String(50))
    statements = db.Column(db.JSON, default=list, nullable=False)
    evidence = db.Column(db.JSON, default=list, nullable=False)
    timeline = db.Column(db.JSON, default=list, nullable=False)
    procedural_assessment = db.Column(db.JSON, default=dict, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utc_now, onupdate=_utc_now)


class SourceRegister(db.Model):
    __tablename__ = "source_registers"

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    source_identifier = db.Column(db.String(80), nullable=True, index=True)
    case_reference = db.Column(db.String(50), nullable=False, index=True)
    source_type = db.Column(db.String(50), nullable=False, default="CITIZEN_SUBMISSION", index=True)
    source_submission_id = db.Column(db.String(50), nullable=True, index=True)
    source_candidate_id = db.Column(db.String(50), nullable=True, index=True)
    source_evidence_ids = db.Column(db.JSON, default=list, nullable=False)
    source_assertion_ids = db.Column(db.JSON, default=list, nullable=False)
    source_claim_ids = db.Column(db.JSON, default=list, nullable=False)
    provenance = db.Column(db.JSON, default=dict, nullable=False)
    register_status = db.Column(db.String(50), nullable=False, default="REGISTERED", index=True)
    authority = db.Column(db.String(100), nullable=True, index=True)
    verification_status = db.Column(db.String(40), nullable=False, default="VERIFIED", index=True)
    source_version = db.Column(db.String(30), nullable=False, default="v1", index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    effective_from = db.Column(db.String(50), nullable=True)
    effective_to = db.Column(db.String(50), nullable=True)
    is_current = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by = db.Column(db.String(100), nullable=True, index=True)
    created_at = db.Column(db.String(50), nullable=False)
    updated_at = db.Column(db.String(50), nullable=True)


class ProcedureRule(db.Model):
    __tablename__ = "procedure_rules"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    rule_code = db.Column(db.String(150), nullable=False, index=True)
    version = db.Column(db.String(30), nullable=False, default="v1", index=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), nullable=False, default="SOURCE_CONTINUITY", index=True)
    description = db.Column(db.Text, nullable=False)
    legal_basis = db.Column(db.Text, nullable=True)
    applicability = db.Column(db.JSON, default=dict, nullable=False)
    required_records = db.Column(db.JSON, default=list, nullable=False)
    required_action = db.Column(db.String(100), nullable=True, index=True)
    source_reference = db.Column(db.String(200), nullable=True, index=True)
    rule_classification = db.Column(db.String(60), nullable=False, default="SYSTEM_CONTROL", index=True)
    trigger = db.Column(db.String(200), nullable=True, index=True)
    ruleset_version = db.Column(db.String(30), nullable=True, index=True)
    severity = db.Column(db.String(30), nullable=False, default="HIGH")
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.String(50), nullable=False)


class ProcedureProfile(db.Model):
    __tablename__ = "procedure_profiles"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    profile_name = db.Column(db.String(100), nullable=False, index=True)
    case_type = db.Column(db.String(50), nullable=False, default="PROCEDURAL_CASE", index=True)
    description = db.Column(db.Text, nullable=True)
    rule_codes = db.Column(db.JSON, default=list, nullable=False)
    default_transition = db.Column(db.String(100), nullable=True)
    version = db.Column(db.String(30), nullable=False, default="v1", index=True)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.String(50), nullable=False)


class CaseProcedureState(db.Model):
    __tablename__ = "case_procedure_states"

    id = db.Column(db.Integer, primary_key=True)
    state_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False, index=True)
    source_id = db.Column(db.String(80), nullable=True, index=True)
    source_identifier = db.Column(db.String(80), nullable=True, index=True)
    source_version = db.Column(db.String(30), nullable=True, index=True)
    rule_id = db.Column(db.String(100), nullable=True, index=True)
    rule_version = db.Column(db.String(30), nullable=True, index=True)
    ruleset_version = db.Column(db.String(30), nullable=True, index=True)
    procedure_version = db.Column(db.String(30), nullable=True, index=True)
    profile_name = db.Column(db.String(100), nullable=False, default="DEFAULT", index=True)
    status = db.Column(db.String(40), nullable=False, default="ACTIVE", index=True)
    gate = db.Column(db.String(50), nullable=False, default="procedure", index=True)
    current_action = db.Column(db.String(100), nullable=True)
    next_permitted_action = db.Column(db.String(200), nullable=True)
    requirement_summary = db.Column(db.JSON, default=dict, nullable=False)
    rule_results = db.Column(db.JSON, default=list, nullable=False)
    source_submission_id = db.Column(db.String(50), nullable=True, index=True)
    source_candidate_id = db.Column(db.String(50), nullable=True, index=True)
    created_by = db.Column(db.String(100), nullable=True, index=True)
    created_at = db.Column(db.String(50), nullable=False)
    updated_at = db.Column(db.String(50), nullable=True)


class ProcedureRequirement(db.Model):
    __tablename__ = "procedure_requirements"

    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    state_id = db.Column(db.String(100), nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False, index=True)
    rule_code = db.Column(db.String(150), nullable=False, index=True)
    rule_version = db.Column(db.String(30), nullable=True, index=True)
    requirement_type = db.Column(db.String(80), nullable=False, default="SOURCE_CHAIN", index=True)
    description = db.Column(db.Text, nullable=False)
    required_action = db.Column(db.String(100), nullable=True, index=True)
    required_record = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(40), nullable=False, default="NOT_STARTED", index=True)
    expected_status = db.Column(db.String(50), nullable=True)
    satisfied = db.Column(db.Boolean, nullable=False, default=False, index=True)
    reason = db.Column(db.Text, nullable=True)
    evidence_reference = db.Column(db.String(200), nullable=True)
    actor_id = db.Column(db.String(100), nullable=True, index=True)
    actor_role = db.Column(db.String(50), nullable=True, index=True)
    history = db.Column(db.JSON, default=list, nullable=False)
    version = db.Column(db.String(30), nullable=False, default="v1", index=True)
    created_at = db.Column(db.String(50), nullable=False)
    updated_at = db.Column(db.String(50), nullable=True)


class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False, index=True)
    officer_id = db.Column(db.String(100), nullable=False)
    officer_role = db.Column(db.String(50), nullable=False)
    assigned_by = db.Column(db.String(100))
    assigned_by_role = db.Column(db.String(50))
    assigned_at = db.Column(db.String(50))
    status = db.Column(db.String(20), default="ACTIVE", nullable=False)
    reason = db.Column(db.Text)
    previous_assignment_id = db.Column(db.String(50))
    assignment_method = db.Column(db.String(30), default="MANUAL", nullable=False)
    selection_rule = db.Column(db.String(100), nullable=True)
    selection_rule_version = db.Column(db.String(30), nullable=True)
    selection_basis = db.Column(db.Text, nullable=True)
    ended_at = db.Column(db.String(50))
    ended_by = db.Column(db.String(100))
    ended_by_role = db.Column(db.String(50))
    end_reason = db.Column(db.Text)
    # M4.3: an ACTIVE assignment is SUSPENDED (write permissions stripped) when
    # a statutory IPID referral freezes the docket; it is reinstated if IPID
    # dismisses the referral and ended if the referral is upheld.
    suspended_at = db.Column(db.String(50))
    suspended_by = db.Column(db.String(100))
    suspension_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=_utc_now)


class Freeze(db.Model):
    __tablename__ = "freezes"

    id = db.Column(db.Integer, primary_key=True)
    freeze_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False, index=True)
    actor_id = db.Column(db.String(100))
    actor_role = db.Column(db.String(50))
    status = db.Column(db.String(20), default="ACTIVE", nullable=False)
    reason = db.Column(db.Text)
    source = db.Column(db.String(50), default="MANUAL")
    related_escalation_id = db.Column(db.String(50))
    frozen_at = db.Column(db.String(50))
    released_at = db.Column(db.String(50))
    released_by = db.Column(db.String(100))
    released_by_role = db.Column(db.String(50))
    release_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=_utc_now)


class AccountabilityProfile(db.Model):
    __tablename__ = "accountability_profiles"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    subject_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    subject_role = db.Column(db.String(50), nullable=False, default="constable")
    total_demerits = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(50), default="NORMAL", nullable=False, index=True)
    access_state = db.Column(db.String(50), default="ACTIVE", nullable=False, index=True)
    threshold_reached = db.Column(db.Boolean, default=False, nullable=False)
    review_required = db.Column(db.Boolean, default=False, nullable=False)
    last_event_id = db.Column(db.String(80), nullable=True)
    last_triggered_at = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.String(50), nullable=False)
    updated_at = db.Column(db.String(50), nullable=False)


class AccountabilityEvent(db.Model):
    __tablename__ = "accountability_events"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(80), unique=True, nullable=False, index=True)
    subject_id = db.Column(db.String(100), nullable=False, index=True)
    subject_role = db.Column(db.String(50), nullable=False, default="constable")
    actor_id = db.Column(db.String(100), nullable=False, index=True)
    actor_role = db.Column(db.String(50), nullable=False)
    event_type = db.Column(db.String(50), nullable=False, default="DEMERIT", index=True)
    delta = db.Column(db.Integer, nullable=False, default=0)
    total_after = db.Column(db.Integer, nullable=False, default=0)
    reason = db.Column(db.Text, nullable=False)
    idempotency_key = db.Column(db.String(200), unique=True, nullable=True, index=True)
    source = db.Column(db.String(50), nullable=False, default="MANUAL")
    metadata_json = db.Column("metadata", db.JSON, default=dict, nullable=False)
    created_at = db.Column(db.String(50), nullable=False)


class Flag(db.Model):
    __tablename__ = "flags"

    id = db.Column(db.Integer, primary_key=True)
    flag_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False, index=True)
    created_by = db.Column(db.String(100))
    created_by_role = db.Column(db.String(50))
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))
    category = db.Column(db.String(100))
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default="OPEN")
    resolution_information = db.Column(db.Text)


class RelatedCase(db.Model):
    __tablename__ = "related_cases"

    id = db.Column(db.Integer, primary_key=True)
    relationship_id = db.Column(db.String(200), unique=True, nullable=False, index=True)
    source_case_reference = db.Column(db.String(50), nullable=False, index=True)
    related_case_reference = db.Column(db.String(50), nullable=False, index=True)
    relationship_type = db.Column(db.String(50))
    created_by = db.Column(db.String(100))
    created_by_role = db.Column(db.String(50))
    created_at = db.Column(db.String(50))
    notes = db.Column(db.Text)


class Investigation(db.Model):
    __tablename__ = "investigations"

    id = db.Column(db.Integer, primary_key=True)
    investigation_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False, index=True)
    detective_id = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(30), default="OPEN", nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))
    outcome = db.Column(db.String(50))
    final_notes = db.Column(db.Text)
    referenced_finding_ids = db.Column(db.JSON, default=list, nullable=False)
    completed_at = db.Column(db.String(50))
    timeline = db.Column(db.JSON, default=list, nullable=False)


class InvestigationFinding(db.Model):
    __tablename__ = "investigation_findings"

    id = db.Column(db.Integer, primary_key=True)
    finding_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    investigation_id = db.Column(db.String(50), nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False)
    detective_id = db.Column(db.String(100))
    finding_type = db.Column(db.String(50))
    notes = db.Column(db.Text)
    reasoning = db.Column(db.Text)
    evidence_ids = db.Column(db.JSON, default=list, nullable=False)
    action_ids = db.Column(db.JSON, default=list, nullable=False)
    referenced_finding_ids = db.Column(db.JSON, default=list, nullable=False)
    claim_ids = db.Column(db.JSON, default=list, nullable=False)
    supporting_material = db.Column(db.JSON, default=list, nullable=False)
    contradicting_material = db.Column(db.JSON, default=list, nullable=False)
    status = db.Column(db.String(30), default="SUBMITTED", nullable=False)
    version = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))
    is_final_outcome = db.Column(db.Boolean, default=False)


class InvestigationNote(db.Model):
    __tablename__ = "investigation_notes"

    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    investigation_id = db.Column(db.String(50), nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False)
    detective_id = db.Column(db.String(100))
    evidence_reference = db.Column(db.String(50))
    note_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.String(50))


class InvestigationAction(db.Model):
    __tablename__ = "investigation_actions"

    id = db.Column(db.Integer, primary_key=True)
    action_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    investigation_id = db.Column(db.String(50), nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False)
    detective_id = db.Column(db.String(100), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    purpose = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    result = db.Column(db.Text, nullable=False)
    record_data = db.Column(db.JSON, default=dict, nullable=False)
    evidence_id = db.Column(db.String(100))
    provenance = db.Column(db.JSON, default=dict, nullable=False)
    performed_at = db.Column(db.String(50))
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))


class Escalation(db.Model):
    __tablename__ = "escalations"

    id = db.Column(db.Integer, primary_key=True)
    escalation_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False, index=True)
    created_by = db.Column(db.String(100))
    created_by_role = db.Column(db.String(50))
    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    status = db.Column(db.String(30), default="OPEN", nullable=False)
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))
    reviewer_id = db.Column(db.String(100))
    reviewer_role = db.Column(db.String(50))
    decision = db.Column(db.String(30))
    decision_by = db.Column(db.String(100))
    decision_by_role = db.Column(db.String(50))
    decision_reason = db.Column(db.Text)
    decision_at = db.Column(db.String(50))
    # M4.3: statutory (IPID Act s28) referral metadata. `source` is MANUAL for
    # ordinary escalations and IPID_STATUTORY_MANDATE for ODDE referrals.
    source = db.Column(db.String(50), default="MANUAL", nullable=False)
    statutory_basis = db.Column(db.Text)
    rule_code = db.Column(db.String(300))
    referral_trigger = db.Column(db.String(50))
    implicated_officer_id = db.Column(db.String(100))


class AuditEvent(db.Model):
    __tablename__ = "audit_events"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    timestamp = db.Column(db.String(50))
    actor_id = db.Column(db.String(100))
    actor_role = db.Column(db.String(50))
    action = db.Column(db.String(100))
    case_reference = db.Column(db.String(50), index=True)
    object_type = db.Column(db.String(50))
    object_id = db.Column(db.String(50))
    previous_state = db.Column(db.String(50))
    new_state = db.Column(db.String(50))
    reason = db.Column(db.Text)
    authorization_context = db.Column(db.Text)
    rule_code = db.Column(db.String(50))
    legal_reference = db.Column(db.Text)
    metadata_json = db.Column("metadata", db.JSON, default=dict)
    details_json = db.Column("details", db.JSON, default=dict)


class Interview(db.Model):
    __tablename__ = "interviews"

    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    case_reference = db.Column(db.String(50), nullable=False, index=True)
    citizen_id = db.Column(db.String(13))
    constable_id = db.Column(db.String(13))
    status = db.Column(db.String(30), default="STARTED")
    start_timestamp = db.Column(db.String(50))
    completion_timestamp = db.Column(db.String(50))
    citizen_recording = db.Column(db.JSON)
    constable_recording = db.Column(db.JSON)
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))


class Recording(db.Model):
    __tablename__ = "recordings"

    id = db.Column(db.Integer, primary_key=True)
    recording_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    interview_id = db.Column(db.String(100), nullable=False, index=True)
    case_reference = db.Column(db.String(50))
    recorder_id = db.Column(db.String(100))
    recorder_role = db.Column(db.String(50))
    recording_type = db.Column(db.String(50))
    status = db.Column(db.String(30))
    filename = db.Column(db.String(200))
    storage_reference = db.Column(db.String(200))
    created_at = db.Column(db.String(50))
    submitted_at = db.Column(db.String(50))


class ReviewNote(db.Model):
    __tablename__ = "review_notes"

    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    escalation_id = db.Column(db.String(50), nullable=False, index=True)
    case_reference = db.Column(db.String(50))
    author_id = db.Column(db.String(100))
    author_role = db.Column(db.String(50))
    note_text = db.Column(db.Text)
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))


class ReviewFinding(db.Model):
    __tablename__ = "review_findings"

    id = db.Column(db.Integer, primary_key=True)
    finding_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    escalation_id = db.Column(db.String(50), nullable=False, index=True)
    case_reference = db.Column(db.String(50))
    author_id = db.Column(db.String(100))
    author_role = db.Column(db.String(50))
    finding_type = db.Column(db.String(50))
    summary = db.Column(db.Text)
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))


class DisciplinaryCase(db.Model):
    __tablename__ = "disciplinary_cases"

    id = db.Column(db.Integer, primary_key=True)
    disciplinary_case_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    source_case_reference = db.Column(db.String(50), nullable=False, index=True)
    escalation_id = db.Column(db.String(50))
    implicated_officer_id = db.Column(db.String(100))
    created_by = db.Column(db.String(100))
    created_by_role = db.Column(db.String(50))
    status = db.Column(db.String(20), default="OPEN")
    reason = db.Column(db.Text)
    category = db.Column(db.String(100))
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))
    # M4.2: objective determination made by the decision engine at uphold time.
    misconduct_tier = db.Column(db.Integer)
    infraction_type = db.Column(db.String(60))
    mandatory_sanction = db.Column(db.String(30))
    determination = db.Column(db.JSON)
    determined_at = db.Column(db.String(50))
    # Closure: any departure from the mandatory sanction needs a justification.
    final_sanction = db.Column(db.String(30))
    deviation_justification = db.Column(db.Text)
    closed_at = db.Column(db.String(50))
    closed_by = db.Column(db.String(100))


class ConflictDeclaration(db.Model):
    """M4.4: a declared conflict of interest (family, business, personal...)
    between an officer and a docket or a party (typically the complainant)."""

    __tablename__ = "conflict_declarations"

    id = db.Column(db.Integer, primary_key=True)
    declaration_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    officer_id = db.Column(db.String(100), nullable=False, index=True)
    officer_role = db.Column(db.String(50))
    case_reference = db.Column(db.String(50), index=True)
    party_id = db.Column(db.String(100), index=True)
    relationship_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="ACTIVE", nullable=False)
    declared_by = db.Column(db.String(100))
    declared_by_role = db.Column(db.String(50))
    declared_at = db.Column(db.String(50))


class IntegrityEvent(db.Model):
    __tablename__ = "integrity_events"

    id = db.Column(db.Integer, primary_key=True)
    integrity_event_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    subject_event_id = db.Column(db.String(50))
    actor_id = db.Column(db.String(100))
    actor_role = db.Column(db.String(50))
    case_reference = db.Column(db.String(50))
    integrity_status = db.Column(db.String(50))
    timestamp = db.Column(db.String(50))
    decision = db.Column(db.Text)
    findings = db.Column(db.JSON, default=dict)
    action_type = db.Column(db.String(50))
    details = db.Column(db.JSON, default=dict)


class EvidenceIndex(db.Model):
    __tablename__ = "evidence_index"

    id = db.Column(db.Integer, primary_key=True)
    evidence_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    case_reference = db.Column(db.String(50))
    uploaded_by = db.Column(db.String(100))
    uploaded_at = db.Column(db.String(50))
    storage_reference = db.Column(db.String(200))
    content_hash = db.Column(db.String(200))
    integrity_status = db.Column(db.String(50))
    chain_of_custody_reference = db.Column(db.String(100))
    created_at = db.Column(db.String(50))
    updated_at = db.Column(db.String(50))
