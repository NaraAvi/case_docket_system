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
    interview_id = db.Column(db.String(100))
    registered_at = db.Column(db.String(50))
    submitted_at = db.Column(db.String(50))
    created_at = db.Column(db.String(50))
    statements = db.Column(db.JSON, default=list, nullable=False)
    evidence = db.Column(db.JSON, default=list, nullable=False)
    timeline = db.Column(db.JSON, default=list, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utc_now, onupdate=_utc_now)


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
