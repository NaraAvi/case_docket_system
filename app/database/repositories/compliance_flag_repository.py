"""Persistence and audit boundary for compliance flags."""

from datetime import UTC, datetime
from uuid import uuid4

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import ComplianceFlag


class ComplianceFlagRepository(BaseSqlAlchemyRepository):
    model = ComplianceFlag
    id_column = "flag_id"
    STATUSES = {"OPEN", "RESPONDED", "CONFIRMED", "DISMISSED"}
    TRANSITIONS = {"OPEN": {"RESPONDED", "CONFIRMED", "DISMISSED"}, "RESPONDED": {"CONFIRMED", "DISMISSED"}, "CONFIRMED": set(), "DISMISSED": set()}

    def __init__(self, session=None, audit_service=None):
        super().__init__(session=session)
        self.audit_service = audit_service

    @staticmethod
    def _now():
        return datetime.now(UTC).isoformat()

    def create(self, payload):
        data = dict(payload)
        data.setdefault("flag_id", f"CF-{uuid4().hex[:16].upper()}")
        data.setdefault("status", "OPEN")
        data.setdefault("raised_at", self._now())
        data.setdefault("evidence", {})
        result = super().create(data)
        self._audit("compliance_flag_created", result, None, result["status"])
        return result

    def list_filtered(self, status=None, rule_code=None, case_reference=None):
        query = self.model.query.order_by(self.model.id.asc())
        if status:
            query = query.filter_by(status=status)
        if rule_code:
            query = query.filter_by(rule_code=rule_code)
        if case_reference:
            query = query.filter_by(case_reference=case_reference)
        return [self._serialize(item) for item in query.all()]

    def transition_status(self, flag_id, status, *, actor_id=None, actor_role=None, response=None, resolution_note=None):
        status = str(status).upper()
        if status not in self.STATUSES:
            raise ValueError("Invalid compliance flag status.")
        current = self.get_by_id(flag_id)
        if current is None:
            return None
        if status not in self.TRANSITIONS.get(current["status"], set()):
            raise ValueError(f"Cannot transition compliance flag from {current['status']} to {status}.")
        now = self._now()
        updates = {"status": status}
        if response is not None:
            updates.update({"officer_response": response, "responded_at": now})
        if status in {"CONFIRMED", "DISMISSED"}:
            updates.update({"resolved_by": actor_id, "resolved_at": now, "resolution_note": resolution_note})
        result = super().update(flag_id, updates)
        self._audit("compliance_flag_status_changed", result, current["status"], status, actor_id, actor_role)
        return result

    def _audit(self, action, flag, previous, new, actor_id=None, actor_role=None):
        if self.audit_service is not None:
            self.audit_service.log({"actor_id": actor_id or "SYSTEM_COMPLIANCE", "actor_role": actor_role or "system_automation", "action": action, "case_reference": flag.get("case_reference"), "object_type": "compliance_flag", "object_id": flag.get("flag_id"), "previous_state": previous, "new_state": new, "rule_code": flag.get("rule_code"), "legal_reference": flag.get("legal_reference_id"), "details": {"status": new}})