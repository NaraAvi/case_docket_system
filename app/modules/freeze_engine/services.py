"""Shared freeze engine for cross-cutting case freeze lifecycle control."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.freeze_repository import FreezeRepository
from app.modules.audit_engine.services import AuditTrailService
from app.services.case_service import CaseService


class FreezeService:
    """Shared case freeze lifecycle used by future oversight and access-control boundaries."""

    VALID_STATUSES = {"ACTIVE", "RELEASED"}

    def __init__(self, repository=None, case_service=None, audit_service=None):
        self.repository = repository or FreezeRepository()
        self.case_service = case_service or CaseService()
        self.audit_service = audit_service or AuditTrailService()

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _get_case(self, case_reference):
        if not case_reference:
            return None
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return case
        return None

    def is_case_frozen(self, case_reference):
        return self.repository.get_current_for_case(case_reference) is not None

    def get_current_freeze(self, case_reference):
        return self.repository.get_current_for_case(case_reference)

    def get_freeze_history(self, case_reference):
        return self.repository.get_history_for_case(case_reference)

    def freeze_case(self, case_reference, actor_id, actor_role, reason=None, source=None, related_escalation_id=None):
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Case not found.")
        if case.get("status") != "REGISTERED":
            raise ValueError("Freeze requires a registered case.")

        current = self.repository.get_current_for_case(case_reference)
        if current is not None and current.get("status") == "ACTIVE":
            raise ValueError("Case is already frozen.")

        freeze = self.repository.create(
            {
                "case_reference": case_reference,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "status": "ACTIVE",
                "reason": reason,
                "source": source or "MANUAL",
                "related_escalation_id": related_escalation_id,
                "frozen_at": self._utc_now(),
                "released_at": None,
                "released_by": None,
                "release_reason": None,
            }
        )
        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": actor_role,
                "action": "case_frozen",
                "case_reference": case_reference,
                "details": {
                    "freeze_id": freeze.get("freeze_id"),
                    "reason": reason,
                    "status": "ACTIVE",
                    "source": freeze.get("source"),
                    "related_escalation_id": related_escalation_id,
                },
            }
        )
        return dict(freeze)

    def get_related_ipid_freeze(self, case_reference, escalation_id=None):
        if not case_reference:
            return None
        for freeze in self.repository.get_history_for_case(case_reference):
            if freeze.get("status") != "ACTIVE":
                continue
            if escalation_id and freeze.get("related_escalation_id") == escalation_id:
                return dict(freeze)
            if freeze.get("source") == "IPID_REVIEW" and (escalation_id is None or freeze.get("related_escalation_id") == escalation_id):
                return dict(freeze)
        return None

    def unfreeze_case(self, case_reference, actor_id, actor_role, reason=None, freeze_id=None):
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Case not found.")

        current = self.repository.get_by_id(freeze_id) if freeze_id else self.repository.get_current_for_case(case_reference)
        if current is None:
            raise ValueError("Case is not currently frozen.")

        current_id = current.get("freeze_id")
        updated = dict(current)
        updated["status"] = "RELEASED"
        updated["released_at"] = self._utc_now()
        updated["released_by"] = actor_id
        updated["release_reason"] = reason
        updated["released_by_role"] = actor_role
        self.repository.update(current_id, updated)
        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": actor_role,
                "action": "case_unfrozen",
                "case_reference": case_reference,
                "details": {
                    "freeze_id": current_id,
                    "reason": reason,
                    "status": "RELEASED",
                    "related_escalation_id": updated.get("related_escalation_id"),
                },
            }
        )
        return dict(updated)

    def assert_access_allowed(self, case_reference, actor_id=None, actor_role=None, operation=None):
        current = self.repository.get_current_for_case(case_reference)
        if current is None:
            return True
        if actor_role in {"station_commander", "citizen"} and operation in {"read", "view"}:
            return True
        if actor_role in {"constable", "detective"} and operation in {"read", "view"}:
            return True
        raise ValueError("Case is frozen and operational mutation is restricted.")
