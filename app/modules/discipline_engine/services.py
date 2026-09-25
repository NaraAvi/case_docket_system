"""Disciplinary case service layer."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.disciplinary_case_repository import DisciplinaryCaseRepository
from app.modules.audit_engine.services import AuditTrailService


class DisciplinaryCaseService:
    """Boundary for internal officer discipline case creation and review."""

    VALID_STATUSES = {"OPEN", "CLOSED"}

    def __init__(self, repository=None, audit_service=None):
        self.repository = repository or DisciplinaryCaseRepository()
        self.audit_service = audit_service or AuditTrailService()

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def create_case(self, source_case_reference, escalation_id, implicated_officer_id, created_by, created_by_role, reason=None, category=None):
        if not source_case_reference:
            raise ValueError("Source case reference is required.")
        if not escalation_id:
            raise ValueError("Escalation reference is required.")
        if not implicated_officer_id:
            raise ValueError("Implicated officer identity is required.")
        if not created_by:
            raise ValueError("Actor identity is required.")

        created = self.repository.create(
            {
                "source_case_reference": str(source_case_reference),
                "escalation_id": str(escalation_id),
                "implicated_officer_id": str(implicated_officer_id),
                "created_by": str(created_by),
                "created_by_role": str(created_by_role or "ipid"),
                "status": "OPEN",
                "reason": reason,
                "category": category or "OFFICER_CONDUCT",
                "created_at": self._utc_now(),
                "updated_at": self._utc_now(),
            }
        )
        self.audit_service.log(
            {
                "actor_id": created_by,
                "actor_role": created_by_role or "ipid",
                "action": "disciplinary_case_created",
                "case_reference": source_case_reference,
                "details": {
                    "disciplinary_case_id": created.get("disciplinary_case_id"),
                    "escalation_id": escalation_id,
                    "implicated_officer_id": implicated_officer_id,
                    "reason": reason,
                },
            }
        )
        return dict(created)

    def list_cases(self):
        return [dict(item) for item in self.repository.list()]

    def get_case(self, disciplinary_case_id):
        case = self.repository.get_by_id(disciplinary_case_id)
        if case is None:
            raise ValueError("Disciplinary case not found.")
        return dict(case)

    def get_for_case(self, case_reference):
        return [dict(item) for item in self.repository.list_for_case(case_reference)]
