"""Escalation engine service layer."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.database.repositories.escalation_repository import EscalationRepository
from app.modules.audit_engine.services import AuditTrailService


class DuplicateEscalationError(ValueError):
    """Raised when a docket already has an unresolved escalation."""

    status_code = 409

    def __init__(self, escalation):
        self.escalation = dict(escalation or {})
        escalation_id = self.escalation.get("escalation_id", "an existing escalation")
        super().__init__(f"This docket already has an unresolved escalation ({escalation_id}).")


class EscalationService:
    """Deterministic escalation workflow for citizen-to-IPID review requests."""

    VALID_CATEGORIES = {
        "REFUSAL_TO_REGISTER",
        "UNLAWFUL_DELAY",
        "OFFICER_CONDUCT",
        "SUSPECTED_MALPRACTICE",
        "OTHER",
    }
    VALID_STATUSES = {"OPEN", "UNDER_REVIEW", "RESOLVED"}
    UNRESOLVED_STATUSES = {"OPEN", "UNDER_REVIEW"}

    def __init__(self, repository=None, audit_service=None):
        self.repository = repository or EscalationRepository()
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
            list_unresolved = getattr(self.repository, "list_unresolved", None)
            escalations = list_unresolved() if list_unresolved is not None else self.repository.list_open()
        escalations.sort(key=lambda item: str(item.get("created_at") or ""))
        return [dict(item) for item in escalations]

    def find_unresolved_for_case(self, case_reference, created_by=None):
        """Return the first unresolved escalation for a docket.

        A docket has a single citizen owner, so the active-ticket invariant is
        case-scoped.  ``created_by`` remains an optional compatibility filter
        for callers that need to inspect a specific actor.
        """
        if created_by is None:
            lookup = getattr(self.repository, "get_unresolved_for_case", None)
            if lookup is not None:
                return lookup(str(case_reference))
        for escalation in self.repository.list_by_case(str(case_reference)):
            if created_by is not None and str(escalation.get("created_by")) != str(created_by):
                continue
            if str(escalation.get("status") or "").upper() in self.UNRESOLVED_STATUSES:
                return dict(escalation)
        return None

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

        existing = self.find_unresolved_for_case(case_reference)
        if existing is not None:
            raise DuplicateEscalationError(existing)

        try:
            escalation = self.repository.create(
                {
                    "case_reference": str(case_reference),
                    "created_by": str(created_by),
                    "created_by_role": str(created_by_role or "citizen"),
                    "category": category_value,
                    "description": description_value,
                    "status": "OPEN",
                    "created_at": self._utc_now(),
                    "updated_at": self._utc_now(),
                }
            )
        except IntegrityError as exc:
            # A concurrent request may win the case-scoped active-ticket
            # unique index between our check and insert.  Surface the same
            # typed conflict rather than leaking a 500/IntegrityError.
            existing = self.find_unresolved_for_case(case_reference)
            if existing is not None:
                raise DuplicateEscalationError(existing) from exc
            raise

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
