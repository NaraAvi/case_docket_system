"""Escalation engine service layer."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.escalation_repository import EscalationRepository
from app.modules.audit_engine.services import AuditTrailService


class EscalationService:
    """Deterministic escalation workflow for citizen-to-IPID review requests."""

    VALID_CATEGORIES = {
        "REFUSAL_TO_REGISTER",
        "UNLAWFUL_DELAY",
        "OFFICER_CONDUCT",
        "SUSPECTED_MALPRACTICE",
        "OTHER",
        "SLA_BREACH",
    }
    # Only the decision engine may raise this category (M4.3); it is
    # deliberately absent from VALID_CATEGORIES so a citizen cannot select it.
    STATUTORY_CATEGORY = "MANDATORY_IPID_REFERRAL"
    SOURCE_MANUAL = "MANUAL"
    SOURCE_STATUTORY = "IPID_STATUTORY_MANDATE"
    SYSTEM_ACTOR_ID = "SYSTEM_ODDE"
    SYSTEM_ACTOR_ROLE = "system_automation"
    VALID_STATUSES = {"OPEN", "UNDER_REVIEW", "RESOLVED"}

    def __init__(self, repository=None, audit_service=None, app=None):
        self.app = app
        self.repository = repository or EscalationRepository(app=app)
        self.audit_service = audit_service or AuditTrailService()

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _normalize_category(value):
        return str(value or "").strip().upper()

    def _serialize_public(self, escalation):
        if escalation is None:
            return None
        return {
            "escalation_id": escalation.get("escalation_id"),
            "case_reference": escalation.get("case_reference"),
            "category": escalation.get("category"),
            "description": escalation.get("description"),
            "status": escalation.get("status"),
            "created_at": escalation.get("created_at"),
            "updated_at": escalation.get("updated_at"),
            "source": escalation.get("source") or self.SOURCE_MANUAL,
            "statutory_basis": escalation.get("statutory_basis"),
        }

    def get_by_id(self, escalation_id):
        return self.repository.get_by_id(escalation_id)

    def _require_under_review(self, escalation, action_name):
        status = str(escalation.get("status") or "").upper()
        if status == "RESOLVED":
            raise ValueError(f"Escalation is already resolved and cannot be {action_name.lower()} again.")
        if status != "UNDER_REVIEW":
            raise ValueError("Escalation must be under review before a decision can be made.")

    def dismiss_escalation(self, escalation_id, actor_id, actor_role="ipid", reason=None):
        escalation = self.repository.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")

        self._require_under_review(escalation, "dismiss")
        updated = dict(escalation)
        updated["status"] = "RESOLVED"
        updated["decision"] = "DISMISSED"
        updated["decision_by"] = actor_id
        updated["decision_by_role"] = actor_role
        updated["decision_reason"] = reason
        updated["decision_at"] = self._utc_now()
        updated["updated_at"] = self._utc_now()
        reviewed = self.repository.update(escalation_id, updated)

        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": actor_role,
                "action": "ipid_escalation_dismissed",
                "case_reference": escalation.get("case_reference"),
                "details": {
                    "escalation_id": escalation_id,
                    "status": "RESOLVED",
                    "decision": "DISMISSED",
                    "decision_reason": reason,
                },
            }
        )
        return dict(reviewed)

    def uphold_escalation(self, escalation_id, actor_id, actor_role="ipid", reason=None):
        escalation = self.repository.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")

        self._require_under_review(escalation, "uphold")
        updated = dict(escalation)
        updated["status"] = "RESOLVED"
        updated["decision"] = "UPHELD"
        updated["decision_by"] = actor_id
        updated["decision_by_role"] = actor_role
        updated["decision_reason"] = reason
        updated["decision_at"] = self._utc_now()
        updated["updated_at"] = self._utc_now()
        reviewed = self.repository.update(escalation_id, updated)

        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": actor_role,
                "action": "ipid_escalation_upheld",
                "case_reference": escalation.get("case_reference"),
                "details": {
                    "escalation_id": escalation_id,
                    "status": "RESOLVED",
                    "decision": "UPHELD",
                    "decision_reason": reason,
                },
            }
        )
        return dict(reviewed)

    def list_for_case(self, case_reference):
        escalations = self.repository.list_by_case(case_reference)
        escalations.sort(key=lambda item: str(item.get("created_at") or ""))
        return [dict(item) for item in escalations]

    def list_queue(self, status=None):
        if status is not None:
            status_value = str(status or "").upper()
            if status_value not in self.VALID_STATUSES:
                raise ValueError("Status filter must be one of: OPEN, UNDER_REVIEW, RESOLVED.")
            escalations = self.repository.list_by_status(status_value)
        else:
            escalations = self.repository.list_unresolved()
        escalations.sort(key=lambda item: str(item.get("created_at") or ""))
        return [dict(item) for item in escalations]

    def create_escalation(self, case_reference, created_by, created_by_role, category, description):
        if not case_reference:
            raise ValueError("Case reference is required.")
        if not created_by:
            raise ValueError("Creator identity is required.")

        category_value = self._normalize_category(category)
        if category_value not in self.VALID_CATEGORIES:
            raise ValueError("Escalation category is invalid.")

        description_value = str(description or "").strip()
        if not description_value:
            raise ValueError("Escalation description is required.")

        escalation = self.repository.create(
            {
                "case_reference": str(case_reference),
                "created_by": str(created_by),
                "created_by_role": str(created_by_role or "citizen"),
                "category": category_value,
                "description": description_value,
                "status": "OPEN",
                "source": self.SOURCE_MANUAL,
                "created_at": self._utc_now(),
                "updated_at": self._utc_now(),
            }
        )

        self.audit_service.log(
            {
                "actor_id": created_by,
                "actor_role": created_by_role or "citizen",
                "action": "escalation_created",
                "case_reference": case_reference,
                "details": {
                    "escalation_id": escalation.get("escalation_id"),
                    "category": category_value,
                    "status": "OPEN",
                },
            }
        )
        return dict(escalation)

    def start_review(self, escalation_id, reviewer_id, reviewer_role="ipid"):
        escalation = self.repository.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")

        status = str(escalation.get("status") or "").upper()
        if status == "UNDER_REVIEW":
            raise ValueError("Escalation is already under review.")
        if status == "RESOLVED":
            raise ValueError("Resolved escalations cannot be reopened in this pack.")

        updated = dict(escalation)
        updated["status"] = "UNDER_REVIEW"
        updated["reviewer_id"] = reviewer_id
        updated["reviewer_role"] = reviewer_role
        updated["updated_at"] = self._utc_now()
        reviewed = self.repository.update(escalation_id, updated)

        self.audit_service.log(
            {
                "actor_id": reviewer_id,
                "actor_role": reviewer_role,
                "action": "ipid_escalation_review_started",
                "case_reference": escalation.get("case_reference"),
                "details": {
                    "escalation_id": escalation_id,
                    "status": "UNDER_REVIEW",
                },
            }
        )
        return dict(reviewed)

    def public_list(self, escalations):
        return [self._serialize_public(item) for item in escalations]

    # ------------------------------------------------------------------
    # Milestone 4.3: statutory (IPID Act s28) referrals
    # ------------------------------------------------------------------
    def list_all(self):
        return [dict(item) for item in self.repository.list()]

    def is_statutory(self, escalation):
        return bool(escalation) and escalation.get("source") == self.SOURCE_STATUTORY

    def find_unresolved_statutory(self, case_reference):
        """Statutory escalations on ``case_reference`` that IPID has not yet
        decided, oldest first."""
        return [
            item
            for item in self.list_for_case(case_reference)
            if self.is_statutory(item) and str(item.get("status") or "").upper() != "RESOLVED"
        ]

    def create_statutory_escalation(
        self,
        case_reference,
        statutory_basis,
        rule_code,
        description,
        trigger,
        implicated_officer_id=None,
    ):
        """Raise an IPID escalation on behalf of the decision engine. The
        creator is the system actor, never a person."""
        if not case_reference:
            raise ValueError("Case reference is required.")
        description_value = str(description or "").strip()
        if not description_value:
            raise ValueError("Escalation description is required.")

        escalation = self.repository.create(
            {
                "case_reference": str(case_reference),
                "created_by": self.SYSTEM_ACTOR_ID,
                "created_by_role": self.SYSTEM_ACTOR_ROLE,
                "category": self.STATUTORY_CATEGORY,
                "description": description_value,
                "status": "OPEN",
                "source": self.SOURCE_STATUTORY,
                "statutory_basis": statutory_basis,
                "rule_code": rule_code,
                "referral_trigger": trigger,
                "implicated_officer_id": str(implicated_officer_id) if implicated_officer_id else None,
                "created_at": self._utc_now(),
                "updated_at": self._utc_now(),
            }
        )
        self.audit_service.log(
            {
                "actor_id": self.SYSTEM_ACTOR_ID,
                "actor_role": self.SYSTEM_ACTOR_ROLE,
                "action": "escalation_created",
                "case_reference": case_reference,
                "rule_code": str(rule_code).split(",")[0] if rule_code else None,
                "legal_reference": statutory_basis,
                "details": {
                    "escalation_id": escalation.get("escalation_id"),
                    "category": self.STATUTORY_CATEGORY,
                    "status": "OPEN",
                    "source": self.SOURCE_STATUTORY,
                    "trigger": trigger,
                },
            }
        )
        return dict(escalation)

    def mark_statutory(self, escalation_id, statutory_basis, rule_code, trigger, implicated_officer_id=None):
        """Upgrade an escalation a person already filed (for example a
        citizen's own complaint) to a statutory referral, without creating a
        duplicate ticket."""
        escalation = self.repository.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")
        updated = dict(escalation)
        updated["source"] = self.SOURCE_STATUTORY
        updated["statutory_basis"] = statutory_basis
        updated["rule_code"] = rule_code
        updated["referral_trigger"] = trigger
        if implicated_officer_id:
            updated["implicated_officer_id"] = str(implicated_officer_id)
        updated["updated_at"] = self._utc_now()
        return dict(self.repository.update(escalation_id, updated))

    def extend_statutory(self, escalation_id, statutory_basis, rule_code, description=None):
        """Fold newly detected s28 categories into the case's existing open
        statutory escalation so one docket never carries duplicate tickets."""
        escalation = self.repository.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")
        updated = dict(escalation)
        updated["statutory_basis"] = statutory_basis
        updated["rule_code"] = rule_code
        if description:
            updated["description"] = f"{escalation.get('description') or ''}\n{description}".strip()
        updated["updated_at"] = self._utc_now()
        return dict(self.repository.update(escalation_id, updated))
