from flask import Flask

from app import models  # noqa: F401  (registers all models with SQLAlchemy metadata)
from app.api.health import health_bp
from app.api.v1.routes import api_v1_bp
from app.auth.service import TestIdentityRegistry, all_seed_identities
from app.ui.routes import ui_bp
from app.config import get_config
from app.database.repositories.audit_event_repository import AuditEventRepository
from app.database.repositories.case_repository import CaseRepository
from app.database.repositories.disciplinary_case_repository import DisciplinaryCaseRepository
from app.database.repositories.review_finding_repository import ReviewFindingRepository
from app.database.repositories.review_note_repository import ReviewNoteRepository
from app.database.repositories.user_repository import UserRepository
from app.extensions import cors, db, jwt, ma, migrate
from app.infrastructure.storage.media_manager import MediaManager
from app.modules.audit_engine.services import AuditTrailService
from app.modules.case_engine.services import DocketManagementService
from app.modules.citizen_engine.services import CitizenAuthenticationService, CitizenDocketService
from app.modules.compliance_engine.services import ComplianceService
from app.modules.constable_engine.services import ConstableRegistrationService
from app.modules.assignment_engine.services import AssignmentService
from app.modules.automation_engine.services import AutomationService
from app.modules.discipline_engine.services import DisciplinaryCaseService
from app.modules.escalation_engine.services import EscalationService
from app.modules.evidence_engine.services import EvidenceManagementService
from app.modules.freeze_engine.services import FreezeService
from app.modules.integrity_engine.services import IntegrityService
from app.modules.investigation_engine.services import InvestigationService
from app.modules.ipid_engine.services import IPIDReviewService
from app.modules.legal_engine.services import LegalReferenceService
from app.modules.regulatory_engine.services import RegulatoryRuleService
from app.modules.station_commander_engine.services import StationCommanderService
from app.services.case_service import CaseService


def create_app(testing: bool = False, database_uri: str | None = None):
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

    user_repository = UserRepository()
    audit_repository = AuditEventRepository()
    with app.app_context():
        db.create_all()
        user_repository.seed_if_empty(all_seed_identities())

    identity_registry = TestIdentityRegistry(user_repository=user_repository)
    citizen_auth_service = CitizenAuthenticationService(identity_provider=identity_registry)
    audit_service = AuditTrailService(repository=audit_repository)
    legal_reference_service = LegalReferenceService()
    regulatory_rule_service = RegulatoryRuleService(legal_reference_service=legal_reference_service)
    case_repository = CaseRepository()
    case_service = CaseService(repository=case_repository)
    docket_manager = DocketManagementService(case_service=case_service)
    citizen_docket_service = CitizenDocketService(
        docket_manager=docket_manager,
        audit_service=audit_service,
        escalation_service=EscalationService(audit_service=audit_service),
    )
    media_manager = MediaManager()
    evidence_service = EvidenceManagementService()
    compliance_service = ComplianceService(
        rule_service=regulatory_rule_service,
        legal_reference_service=legal_reference_service,
    )
    integrity_service = IntegrityService(audit_service=audit_service, evidence_service=evidence_service)
    constable_registration_service = ConstableRegistrationService(
        case_service=case_service,
        audit_service=audit_service,
        media_manager=media_manager,
        evidence_service=evidence_service,
    )
    freeze_service = FreezeService(case_service=case_service, audit_service=audit_service)
    investigation_service = InvestigationService(
        case_service=case_service,
        audit_service=audit_service,
        constable_service=constable_registration_service,
        freeze_service=freeze_service,
    )
    assignment_service = AssignmentService(
        case_service=case_service,
        audit_service=audit_service,
        identity_registry=identity_registry,
        freeze_service=freeze_service,
    )
    constable_registration_service.freeze_service = freeze_service
    automation_service = AutomationService(
        case_service=case_service,
        assignment_service=assignment_service,
        audit_service=audit_service,
        freeze_service=freeze_service,
    )
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
    )
    escalation_service = EscalationService(audit_service=audit_service)
    review_note_repository = ReviewNoteRepository()
    review_finding_repository = ReviewFindingRepository()
    disciplinary_case_repository = DisciplinaryCaseRepository()
    disciplinary_case_service = DisciplinaryCaseService(repository=disciplinary_case_repository, audit_service=audit_service)
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
    )

    app.extensions["identity_registry"] = identity_registry
    app.extensions["citizen_auth_service"] = citizen_auth_service
    app.extensions["audit_service"] = audit_service
    app.extensions["legal_reference_service"] = legal_reference_service
    app.extensions["regulatory_rule_service"] = regulatory_rule_service
    app.extensions["compliance_service"] = compliance_service
    app.extensions["integrity_service"] = integrity_service
    app.extensions["case_service"] = case_service
    app.extensions["assignment_service"] = assignment_service
    app.extensions["freeze_service"] = freeze_service
    app.extensions["automation_service"] = automation_service
    app.extensions["citizen_docket_service"] = citizen_docket_service
    app.extensions["constable_registration_service"] = constable_registration_service
    app.extensions["investigation_service"] = investigation_service
    app.extensions["station_commander_service"] = station_commander_service
    app.extensions["escalation_service"] = escalation_service
    app.extensions["disciplinary_case_service"] = disciplinary_case_service
    app.extensions["ipid_service"] = ipid_service
    app.extensions["media_manager"] = media_manager

    app.register_blueprint(health_bp)
    app.register_blueprint(api_v1_bp)
    app.register_blueprint(ui_bp)

    return app
