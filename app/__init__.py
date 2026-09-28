import os
import tempfile

import sqlalchemy
from flask import Flask

from app import models  # noqa: F401  (registers all models with SQLAlchemy metadata)
from app.api.health import health_bp
from app.api.v1.routes import api_v1_bp
from app.auth.service import TestIdentityRegistry, all_seed_identities
from app.ui.routes import ui_bp
from app.config import get_config
from app.database.repositories.accountability_repository import AccountabilityEventRepository, AccountabilityProfileRepository
from app.database.repositories.assertion_repository import AssertionRepository, ClaimRepository
from app.database.repositories.audit_event_repository import AuditEventRepository
from app.database.repositories.case_repository import CaseRepository
from app.database.repositories.conflict_declaration_repository import ConflictDeclarationRepository
from app.database.repositories.disciplinary_case_repository import DisciplinaryCaseRepository
from app.database.repositories.incident_candidate_repository import IncidentCandidateRepository, RelationshipRepository
from app.database.repositories.procedure_repository import (
    CaseProcedureStateRepository,
    ProcedureProfileRepository,
    ProcedureRequirementRepository,
    ProcedureRuleRepository,
    SourceRegisterRepository,
)
from app.database.repositories.review_finding_repository import ReviewFindingRepository
from app.database.repositories.review_note_repository import ReviewNoteRepository
from app.database.repositories.submission_repository import (
    ControlEvaluationRepository,
    RuleEvaluationRepository,
    SubmissionCorrectionRepository,
    SubmissionEventRepository,
    SubmissionEvidenceRepository,
    SubmissionRepository,
    WithdrawalRequestRepository,
)
from app.database.repositories.user_repository import UserRepository
from app.extensions import cors, db, jwt, ma, migrate
from app.infrastructure.storage.media_manager import MediaManager
from app.modules.accountability_engine.services import AccountabilityService, AccountabilityGate
from app.modules.audit_engine.services import AuditTrailService
from app.modules.case_engine.services import DocketManagementService
from app.modules.citizen_engine.services import CitizenAuthenticationService, CitizenDocketService, CitizenSubmissionService
from app.modules.compliance_engine.services import ComplianceService
from app.modules.constable_engine.services import ConstableRegistrationService
from app.modules.control_gate import (
    CaseCreationGate,
    ConflictGate,
    FreezeGate,
    InterviewGate,
    InvestigationCompletionGate,
    InvestigationGate,
    RegistrationGate,
)
from app.modules.decision_engine import ConflictOfInterestService, ObjectiveDecisionEngine, StatutoryReferralService
from app.modules.assignment_engine.services import AssignmentService
from app.modules.automation_engine.services import AutomationService
from app.modules.discipline_engine.services import DisciplinaryCaseService
from app.modules.escalation_engine.services import EscalationService
from app.modules.evidence_engine.services import EvidenceManagementService
from app.modules.freeze_engine.services import FreezeService
from app.modules.integrity_engine.services import IntegrityService
from app.modules.incident_engine.services import IncidentCandidateService
from app.modules.investigation_engine.services import InvestigationService
from app.modules.ipid_engine.services import IPIDReviewService
from app.modules.legal_engine.services import LegalReferenceService
from app.modules.procedure_engine.services import DetectiveProcedureService
from app.modules.regulatory_engine.services import RegulatoryRuleService
import atexit

from app.modules.station_commander_engine.services import StationCommanderService
from app.modules.transcription_engine.services import RecordingComparisonEngine, TranscriptGenerationService, WhisperXProvider
from app.scheduler import shutdown_sla_scheduler, start_sla_scheduler
from app.services.case_service import CaseService


def _ensure_assignment_schema(app: Flask):
    """Backfill persisted SQLite schema for newer assignment metadata.

    The live project database can predate the most recent assignment-model
    fields, and `db.create_all()` does not add columns to an existing table.
    This compatibility check preserves existing case data while ensuring the
    newer assignment metadata is available to the runtime.
    """
    with app.app_context():
        inspector = sqlalchemy.inspect(db.engine)
        if not inspector.has_table("assignments"):
            return

        columns = {column["name"] for column in inspector.get_columns("assignments")}
        additions = {
            "assignment_method": "VARCHAR(30) DEFAULT 'MANUAL' NOT NULL",
            "selection_rule": "VARCHAR(100)",
            "selection_rule_version": "VARCHAR(30)",
            "selection_basis": "TEXT",
        }
        missing = {name: definition for name, definition in additions.items() if name not in columns}
        if not missing:
            return

        connection = db.engine.raw_connection()
        try:
            cursor = connection.cursor()
            for name, definition in missing.items():
                cursor.execute(f"ALTER TABLE assignments ADD COLUMN {name} {definition}")
            connection.commit()
        finally:
            connection.close()


def _ensure_procedure_schema(app: Flask):
    """Backfill procedure tables for persistent SQLite installs.

    The runtime database can predate the Slice 0B fields. `db.create_all()` does
    not add missing columns to an existing database, so these compatibility
    checks preserve historical data while adding the newer procedure metadata.
    """
    with app.app_context():
        inspector = sqlalchemy.inspect(db.engine)
        table_columns = {
            "source_registers": {
                "source_identifier": "VARCHAR(80)",
                "authority": "VARCHAR(100)",
                "verification_status": "VARCHAR(40) DEFAULT 'VERIFIED'",
                "source_version": "VARCHAR(30) DEFAULT 'v1'",
                "effective_from": "VARCHAR(50)",
                "effective_to": "VARCHAR(50)",
                "is_current": "BOOLEAN DEFAULT 1",
            },
            "procedure_rules": {
                "source_reference": "VARCHAR(200)",
                "rule_classification": "VARCHAR(60) DEFAULT 'SYSTEM_CONTROL'",
                "trigger": "VARCHAR(200)",
                "ruleset_version": "VARCHAR(30)",
            },
            "case_procedure_states": {
                "source_identifier": "VARCHAR(80)",
                "source_version": "VARCHAR(30)",
                "rule_id": "VARCHAR(100)",
                "rule_version": "VARCHAR(30)",
                "ruleset_version": "VARCHAR(30)",
                "procedure_version": "VARCHAR(30)",
            },
            "procedure_requirements": {
                "rule_version": "VARCHAR(30)",
                "required_action": "VARCHAR(100)",
                "state": "VARCHAR(40) DEFAULT 'NOT_STARTED'",
                "reason": "TEXT",
                "actor_id": "VARCHAR(100)",
                "actor_role": "VARCHAR(50)",
                "history": "JSON",
            },
        }
        for table_name, additions in table_columns.items():
            if not inspector.has_table(table_name):
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing = {name: definition for name, definition in additions.items() if name not in columns}
            if not missing:
                continue
            connection = db.engine.raw_connection()
            try:
                cursor = connection.cursor()
                for name, definition in missing.items():
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")
                connection.commit()
            finally:
                connection.close()


def _ensure_investigation_action_schema(app: Flask):
    """Backfill investigation action payload fields for SQLite installs created before the record-data schema landed."""
    with app.app_context():
        inspector = sqlalchemy.inspect(db.engine)
        if not inspector.has_table("investigation_actions"):
            return

        columns = {column["name"] for column in inspector.get_columns("investigation_actions")}
        if "record_data" in columns:
            return

        connection = db.engine.raw_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("ALTER TABLE investigation_actions ADD COLUMN record_data JSON DEFAULT '{}' NOT NULL")
            connection.commit()
        finally:
            connection.close()


def _ensure_investigation_reference_schema(app: Flask):
    """Backfill persisted detective reference arrays for saved findings and completion basis."""
    with app.app_context():
        inspector = sqlalchemy.inspect(db.engine)
        table_columns = {
            "investigations": {
                "referenced_finding_ids": "JSON DEFAULT '[]' NOT NULL",
            },
            "investigation_findings": {
                "action_ids": "JSON DEFAULT '[]' NOT NULL",
                "referenced_finding_ids": "JSON DEFAULT '[]' NOT NULL",
            },
        }
        for table_name, additions in table_columns.items():
            if not inspector.has_table(table_name):
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing = {name: definition for name, definition in additions.items() if name not in columns}
            if not missing:
                continue
            connection = db.engine.raw_connection()
            try:
                cursor = connection.cursor()
                for name, definition in missing.items():
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")
                connection.commit()
            finally:
                connection.close()


def _reconcile_registered_case_assignments(app: Flask):
    """Backfill initial detective assignments for pre-existing registered cases."""
    with app.app_context():
        assignment_service = app.extensions.get("assignment_service")
        case_service = app.extensions.get("case_service")
        if assignment_service is None or case_service is None:
            return

        for case in case_service.get_all_cases():
            case_reference = case.get("case_reference")
            if not case_reference:
                continue
            if str(case.get("status") or "").upper() != "REGISTERED":
                continue
            try:
                assignment_service.ensure_initial_detective_assignment(
                    case_reference,
                    actor_id="system",
                    actor_role="system",
                    reason="Reconciliation for already-registered docket with no active detective assignment.",
                )
            except ValueError:
                app.logger.warning("Skipping automatic detective reconciliation for %s", case_reference)


def create_app(testing: bool = False, database_uri: str | None = None, upload_storage_root: str | None = None):
    app = Flask(__name__)
    config = get_config()
    app.config.from_object(config)

    if testing:
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = database_uri or "sqlite:///:memory:"
    elif database_uri:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_uri

    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    ma.init_app(app)

    user_repository = UserRepository(app=app)
    audit_repository = AuditEventRepository(app=app)
    with app.app_context():
        db.create_all()
        _ensure_assignment_schema(app)
        _ensure_procedure_schema(app)
        _ensure_investigation_action_schema(app)
        _ensure_investigation_reference_schema(app)
        user_repository.seed_if_empty(all_seed_identities())

    identity_registry = TestIdentityRegistry(user_repository=user_repository)
    citizen_auth_service = CitizenAuthenticationService(identity_provider=identity_registry)
    audit_service = AuditTrailService(repository=audit_repository)
    legal_reference_service = LegalReferenceService()
    regulatory_rule_service = RegulatoryRuleService(legal_reference_service=legal_reference_service)
    case_repository = CaseRepository(app=app)
    case_service = CaseService(repository=case_repository, app=app)
    docket_manager = DocketManagementService(case_service=case_service, app=app)
    citizen_docket_service = CitizenDocketService(
        docket_manager=docket_manager,
        audit_service=audit_service,
        escalation_service=EscalationService(audit_service=audit_service, app=app),
        app=app,
    )
    submission_repository = SubmissionRepository(app=app)
    submission_event_repository = SubmissionEventRepository(app=app)
    assertion_repository = AssertionRepository(app=app)
    claim_repository = ClaimRepository(app=app)
    rule_evaluation_repository = RuleEvaluationRepository(app=app)
    control_evaluation_repository = ControlEvaluationRepository(app=app)
    evidence_repository = SubmissionEvidenceRepository(app=app)
    correction_repository = SubmissionCorrectionRepository(app=app)
    withdrawal_repository = WithdrawalRequestRepository(app=app)
    citizen_submission_service = CitizenSubmissionService(
        repository=submission_repository,
        event_repository=submission_event_repository,
        assertion_repository=assertion_repository,
        claim_repository=claim_repository,
        evidence_repository=evidence_repository,
        correction_repository=correction_repository,
        withdrawal_repository=withdrawal_repository,
        audit_service=audit_service,
        app=app,
    )
    if upload_storage_root:
        storage_root = upload_storage_root
    elif testing:
        storage_root = tempfile.mkdtemp(prefix="pdas_uploads_")
    else:
        storage_root = os.path.join(app.instance_path, "uploads")
    media_manager = MediaManager(storage_root=storage_root)
    transcript_service = TranscriptGenerationService(provider=WhisperXProvider())
    recording_comparison_engine = RecordingComparisonEngine()
    evidence_service = EvidenceManagementService()
    compliance_service = ComplianceService(
        rule_service=regulatory_rule_service,
        legal_reference_service=legal_reference_service,
    )
    integrity_service = IntegrityService(audit_service=audit_service, evidence_service=evidence_service)
    freeze_service = FreezeService(case_service=case_service, audit_service=audit_service, app=app)
    freeze_gate = FreezeGate(freeze_service=freeze_service)
    constable_registration_service = ConstableRegistrationService(
        case_service=case_service,
        audit_service=audit_service,
        media_manager=media_manager,
        evidence_service=evidence_service,
        freeze_service=freeze_service,
        freeze_gate=freeze_gate,
        app=app,
    )
    citizen_docket_service.freeze_service = freeze_service
    assignment_service = AssignmentService(
        case_service=case_service,
        audit_service=audit_service,
        identity_registry=identity_registry,
        freeze_service=freeze_service,
        app=app,
    )
    investigation_service = InvestigationService(
        case_service=case_service,
        audit_service=audit_service,
        constable_service=constable_registration_service,
        freeze_service=freeze_service,
        assignment_service=assignment_service,
        app=app,
    )
    constable_registration_service.freeze_service = freeze_service
    constable_registration_service.assignment_service = assignment_service
    review_note_repository = ReviewNoteRepository(app=app)
    review_finding_repository = ReviewFindingRepository(app=app)
    disciplinary_case_repository = DisciplinaryCaseRepository(app=app)
    disciplinary_case_service = DisciplinaryCaseService(repository=disciplinary_case_repository, audit_service=audit_service)
    accountability_profile_repository = AccountabilityProfileRepository(app=app)
    accountability_event_repository = AccountabilityEventRepository(app=app)
    accountability_service = AccountabilityService(
        profile_repository=accountability_profile_repository,
        event_repository=accountability_event_repository,
        audit_service=audit_service,
        identity_registry=identity_registry,
        app=app,
    )
    accountability_gate = AccountabilityGate(accountability_service=accountability_service)
    escalation_service = EscalationService(audit_service=audit_service, app=app)
    decision_engine = ObjectiveDecisionEngine(
        case_service=case_service,
        assignment_service=assignment_service,
        investigation_service=investigation_service,
        freeze_service=freeze_service,
        disciplinary_service=disciplinary_case_service,
        audit_service=audit_service,
    )
    automation_service = AutomationService(
        case_service=case_service,
        assignment_service=assignment_service,
        audit_service=audit_service,
        freeze_service=freeze_service,
        decision_engine=decision_engine,
        escalation_service=escalation_service,
        app=app,
    )
    automation_service.register("sla_breach_guard", automation_service.list_breaches)
    station_commander_service = StationCommanderService(
        case_service=case_service,
        audit_service=audit_service,
        identity_registry=identity_registry,
        assignment_service=assignment_service,
        freeze_service=freeze_service,
        automation_service=automation_service,
        evidence_service=evidence_service,
        constable_service=constable_registration_service,
        investigation_service=investigation_service,
        media_manager=media_manager,
        app=app,
    )

    # --- Milestone 4: Objective Deterministic Decision Engine -------------------
    conflict_declaration_repository = ConflictDeclarationRepository(app=app)
    statutory_referral_service = StatutoryReferralService(
        decision_engine=decision_engine,
        case_service=case_service,
        escalation_service=escalation_service,
        freeze_service=freeze_service,
        assignment_service=assignment_service,
        audit_service=audit_service,
        integrity_service=integrity_service,
    )
    conflict_service = ConflictOfInterestService(
        case_service=case_service,
        assignment_service=assignment_service,
        escalation_service=escalation_service,
        disciplinary_service=disciplinary_case_service,
        declaration_repository=conflict_declaration_repository,
        identity_registry=identity_registry,
        constable_service=constable_registration_service,
        audit_service=audit_service,
    )
    conflict_gate = ConflictGate(conflict_service=conflict_service)
    interview_gate = InterviewGate(freeze_service=freeze_service, conflict_service=conflict_service)
    registration_gate = RegistrationGate(freeze_service=freeze_service, conflict_service=conflict_service)
    investigation_gate = InvestigationGate(freeze_service=freeze_service, conflict_service=conflict_service, case_service=case_service)
    investigation_completion_gate = InvestigationCompletionGate(
        freeze_service=freeze_service,
        conflict_service=conflict_service,
        case_service=case_service,
    )
    constable_registration_service.conflict_gate = conflict_gate
    constable_registration_service.interview_gate = interview_gate
    constable_registration_service.registration_gate = registration_gate
    # M4.3: citizen submissions/escalations and constable flags are screened.
    citizen_docket_service.referral_service = statutory_referral_service
    constable_registration_service.referral_service = statutory_referral_service
    # M4.4: assignments, docket opening and investigation opening enforce recusal.
    assignment_service.conflict_service = conflict_service
    constable_registration_service.conflict_service = conflict_service
    investigation_service.conflict_service = conflict_service

    ipid_service = IPIDReviewService(
        case_service=case_service,
        audit_service=audit_service,
        escalation_service=escalation_service,
        assignment_service=assignment_service,
        freeze_service=freeze_service,
        constable_service=constable_registration_service,
        investigation_service=investigation_service,
        review_note_repository=review_note_repository,
        review_finding_repository=review_finding_repository,
        identity_registry=identity_registry,
        disciplinary_service=disciplinary_case_service,
        decision_engine=decision_engine,
        app=app,
    )
    incident_candidate_repository = IncidentCandidateRepository(app=app)
    relationship_repository = RelationshipRepository(app=app)
    source_register_repository = SourceRegisterRepository(app=app)
    procedure_rule_repository = ProcedureRuleRepository(app=app)
    procedure_profile_repository = ProcedureProfileRepository(app=app)
    case_procedure_state_repository = CaseProcedureStateRepository(app=app)
    procedure_requirement_repository = ProcedureRequirementRepository(app=app)
    case_creation_gate = CaseCreationGate(case_service=case_service)
    incident_candidate_service = IncidentCandidateService(
        app=app,
        submission_repository=submission_repository,
        assertion_repository=assertion_repository,
        claim_repository=claim_repository,
        candidate_repository=incident_candidate_repository,
        relationship_repository=relationship_repository,
        rule_evaluation_repository=rule_evaluation_repository,
        control_evaluation_repository=control_evaluation_repository,
        audit_service=audit_service,
        citizen_submission_service=citizen_submission_service,
        case_service=case_service,
        case_creation_gate=case_creation_gate,
    )
    constable_registration_service.citizen_submission_service = citizen_submission_service
    constable_registration_service.incident_candidate_service = incident_candidate_service
    detective_procedure_service = DetectiveProcedureService(
        app=app,
        case_service=case_service,
        audit_service=audit_service,
        source_repository=source_register_repository,
        rule_repository=procedure_rule_repository,
        profile_repository=procedure_profile_repository,
        state_repository=case_procedure_state_repository,
        requirement_repository=procedure_requirement_repository,
        citizen_submission_service=citizen_submission_service,
        incident_candidate_service=incident_candidate_service,
        assignment_service=assignment_service,
    )

    app.extensions["identity_registry"] = identity_registry
    app.extensions["citizen_auth_service"] = citizen_auth_service
    app.extensions["citizen_submission_service"] = citizen_submission_service
    app.extensions["submission_repository"] = submission_repository
    app.extensions["submission_event_repository"] = submission_event_repository
    app.extensions["assertion_repository"] = assertion_repository
    app.extensions["claim_repository"] = claim_repository
    app.extensions["rule_evaluation_repository"] = rule_evaluation_repository
    app.extensions["control_evaluation_repository"] = control_evaluation_repository
    app.extensions["evidence_repository"] = evidence_repository
    app.extensions["correction_repository"] = correction_repository
    app.extensions["withdrawal_repository"] = withdrawal_repository
    app.extensions["incident_candidate_repository"] = incident_candidate_repository
    app.extensions["relationship_repository"] = relationship_repository
    app.extensions["case_creation_gate"] = case_creation_gate
    app.extensions["incident_candidate_service"] = incident_candidate_service
    app.extensions["source_register_repository"] = source_register_repository
    app.extensions["procedure_rule_repository"] = procedure_rule_repository
    app.extensions["procedure_profile_repository"] = procedure_profile_repository
    app.extensions["case_procedure_state_repository"] = case_procedure_state_repository
    app.extensions["procedure_requirement_repository"] = procedure_requirement_repository
    app.extensions["detective_procedure_service"] = detective_procedure_service
    app.extensions["procedure_service"] = detective_procedure_service
    app.extensions["audit_service"] = audit_service
    app.extensions["accountability_service"] = accountability_service
    app.extensions["accountability_gate"] = accountability_gate
    app.extensions["legal_reference_service"] = legal_reference_service
    app.extensions["regulatory_rule_service"] = regulatory_rule_service
    app.extensions["compliance_service"] = compliance_service
    app.extensions["integrity_service"] = integrity_service
    app.extensions["case_service"] = case_service
    app.extensions["assignment_service"] = assignment_service
    app.extensions["freeze_service"] = freeze_service
    app.extensions["freeze_gate"] = freeze_gate
    app.extensions["conflict_gate"] = conflict_gate
    app.extensions["interview_gate"] = interview_gate
    app.extensions["registration_gate"] = registration_gate
    app.extensions["investigation_gate"] = investigation_gate
    app.extensions["investigation_completion_gate"] = investigation_completion_gate
    app.extensions["automation_service"] = automation_service
    app.extensions["citizen_docket_service"] = citizen_docket_service
    app.extensions["constable_registration_service"] = constable_registration_service
    app.extensions["investigation_service"] = investigation_service
    app.extensions["investigation_action_repository"] = investigation_service.action_repository
    app.extensions["station_commander_service"] = station_commander_service
    app.extensions["escalation_service"] = escalation_service
    app.extensions["disciplinary_case_service"] = disciplinary_case_service
    app.extensions["ipid_service"] = ipid_service
    app.extensions["decision_engine"] = decision_engine
    app.extensions["statutory_referral_service"] = statutory_referral_service
    app.extensions["conflict_service"] = conflict_service
    app.extensions["media_manager"] = media_manager
    app.extensions["transcript_service"] = transcript_service
    app.extensions["transcription_service"] = transcript_service
    app.extensions["recording_comparison_engine"] = recording_comparison_engine
    app.extensions["comparison_engine"] = recording_comparison_engine
    app.extensions["sla_scheduler"] = None
    _reconcile_registered_case_assignments(app)
    app.config.setdefault("SLA_SCHEDULER_INTERVAL_SECONDS", 60)
    if not testing:
        start_sla_scheduler(app, interval_seconds=app.config["SLA_SCHEDULER_INTERVAL_SECONDS"])
    atexit.register(shutdown_sla_scheduler, app)

    @app.before_request
    def _run_registered_automation_jobs():
        automation_service = app.extensions.get("automation_service")
        if automation_service is None:
            return
        try:
            automation_service.trigger_registered_jobs()
        except Exception:
            app.logger.exception("Automation job trigger failed during request handling")

    app.register_blueprint(health_bp)
    app.register_blueprint(api_v1_bp)
    app.register_blueprint(ui_bp)

    return app
