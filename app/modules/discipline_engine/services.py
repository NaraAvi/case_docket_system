"""Disciplinary case service layer."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.disciplinary_case_repository import DisciplinaryCaseRepository
from app.modules.audit_engine.services import AuditTrailService


class DisciplinaryCaseService:
    """Boundary for internal officer discipline case creation and review."""

    VALID_STATUSES = {"OPEN", "CLOSED"}
    VALID_SANCTIONS = {"WARNING", "FINAL_WARNING", "SUSPENSION", "DISMISSAL", "NO_SANCTION"}

    def __init__(self, repository=None, audit_service=None, app=None):
        self.app = app
        self.repository = repository or DisciplinaryCaseRepository(app=app)
        self.audit_service = audit_service or AuditTrailService()

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def create_case(
        self,
        source_case_reference,
        escalation_id,
        implicated_officer_id,
        created_by,
        created_by_role,
        reason=None,
        category=None,
        determination=None,
    ):
        if not source_case_reference:
            raise ValueError("Source case reference is required.")
        if not escalation_id:
            raise ValueError("Escalation reference is required.")
        if not implicated_officer_id:
            raise ValueError("Implicated officer identity is required.")
        if not created_by:
            raise ValueError("Actor identity is required.")

        existing = self.repository.get_for_escalation(escalation_id)
        if existing is not None:
            if str(existing.get("source_case_reference") or "") != str(source_case_reference):
                raise ValueError("Disciplinary case already exists for this escalation with a different case reference.")
            return dict(existing)

        record = {
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
        if determination:
            record.update(
                {
                    "misconduct_tier": determination.get("misconduct_tier"),
                    "infraction_type": determination.get("infraction_type"),
                    "mandatory_sanction": determination.get("mandatory_sanction"),
                    "determination": determination,
                    "determined_at": determination.get("determined_at") or self._utc_now(),
                }
            )
        created = self.repository.create(record)
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
        if determination:
            self.audit_service.log(
                {
                    "actor_id": created_by,
                    "actor_role": created_by_role or "ipid",
                    "action": "odde_sanction_determined",
                    "case_reference": source_case_reference,
                    "rule_code": "SAPS.DISCIPLINE.SANCTION_MATRIX",
                    "legal_reference": "SAPS Discipline Regulations, 2016 (prototype codification)",
                    "details": {
                        "disciplinary_case_id": created.get("disciplinary_case_id"),
                        "implicated_officer_id": implicated_officer_id,
                        "infraction_type": determination.get("infraction_type"),
                        "misconduct_tier": determination.get("misconduct_tier"),
                        "mandatory_sanction": determination.get("mandatory_sanction"),
                        "prior_count": (determination.get("sanction") or {}).get("prior_count"),
                        "engine_version": determination.get("engine_version"),
                        "corpus_version": determination.get("corpus_version"),
                    },
                }
            )
        return dict(created)

    def close_case(self, disciplinary_case_id, closed_by, final_sanction=None, justification=None):
        """Close a disciplinary case. The hearing outcome defaults to the
        mandatory sanction; any departure from it (either direction) must
        carry a written justification, which becomes part of the record."""
        existing = self.repository.get_by_id(disciplinary_case_id)
        if existing is None:
            raise ValueError("Disciplinary case not found.")
        if str(existing.get("status") or "").upper() == "CLOSED":
            raise ValueError("Disciplinary case is already closed.")
        if not closed_by:
            raise ValueError("Actor identity is required.")

        mandatory = existing.get("mandatory_sanction")
        outcome = str(final_sanction or mandatory or "").strip().upper()
        if not outcome:
            raise ValueError("Final sanction is required.")
        if outcome not in self.VALID_SANCTIONS:
            raise ValueError("Final sanction is invalid.")

        justification_text = str(justification or "").strip()
        deviates = bool(mandatory) and outcome != mandatory
        if deviates and not justification_text:
            raise ValueError("A written justification is required to depart from the mandatory sanction.")

        now = self._utc_now()
        updated = dict(existing)
        updated.update(
            {
                "status": "CLOSED",
                "final_sanction": outcome,
                "deviation_justification": justification_text or None,
                "closed_at": now,
                "closed_by": str(closed_by),
                "updated_at": now,
            }
        )
        saved = self.repository.update(disciplinary_case_id, updated)
        self.audit_service.log(
            {
                "actor_id": closed_by,
                "actor_role": "ipid",
                "action": "disciplinary_case_closed",
                "case_reference": existing.get("source_case_reference"),
                "rule_code": "SAPS.DISCIPLINE.SANCTION_MATRIX" if mandatory else None,
                "details": {
                    "disciplinary_case_id": disciplinary_case_id,
                    "implicated_officer_id": existing.get("implicated_officer_id"),
                    "mandatory_sanction": mandatory,
                    "final_sanction": outcome,
                    "deviated_from_mandatory": deviates,
                    "deviation_justification": justification_text or None,
                },
            }
        )
        return dict(saved)

    def list_cases(self):
        return [dict(item) for item in self.repository.list()]

    def list_open_for_officer(self, officer_id):
        return [
            dict(item)
            for item in self.repository.list_for_officer(officer_id)
            if str(item.get("status") or "").upper() == "OPEN"
        ]

    def get_case(self, disciplinary_case_id):
        case = self.repository.get_by_id(disciplinary_case_id)
        if case is None:
            raise ValueError("Disciplinary case not found.")
        return dict(case)

    def get_for_case(self, case_reference):
        return [dict(item) for item in self.repository.list_for_case(case_reference)]
