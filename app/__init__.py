import os
import tempfile

from flask import Flask

from app import models  # noqa: F401  (registers all models with SQLAlchemy metadata)
from app.api.health import health_bp
from app.api.v1.routes import api_v1_bp
from app.auth.service import TestIdentityRegistry, all_seed_identities
from app.ui.routes import ui_bp
from app.config import get_config
from app.database.repositories.assertion_repository import AssertionRepository, ClaimRepository
from app.database.repositories.audit_event_repository import AuditEventRepository
from app.database.repositories.case_repository import CaseRepository
from app.database.repositories.conflict_declaration_repository import ConflictDeclarationRepository
from app.database.repositories.disciplinary_case_repository import DisciplinaryCaseRepository
from app.database.repositories.incident_candidate_repository import IncidentCandidateRepository, RelationshipRepository
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
from app.modules.regulatory_engine.services import RegulatoryRuleService
import atexit

from app.modules.station_commander_engine.services import StationCommanderService
from app.scheduler import shutdown_sla_scheduler, start_sla_scheduler
from app.services.case_service import CaseService


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
    app.extensions["audit_service"] = audit_service
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
    app.extensions["station_commander_service"] = station_commander_service
    app.extensions["escalation_service"] = escalation_service
    app.extensions["disciplinary_case_service"] = disciplinary_case_service
    app.extensions["ipid_service"] = ipid_service
    app.extensions["decision_engine"] = decision_engine
    app.extensions["statutory_referral_service"] = statutory_referral_service
    app.extensions["conflict_service"] = conflict_service
    app.extensions["media_manager"] = media_manager
    app.extensions["sla_scheduler"] = None
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
