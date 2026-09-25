"""Repository boundary for IPID escalation persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import Escalation


class EscalationRepository(BaseSqlAlchemyRepository):
    """Persistence for escalation records."""

    model = Escalation
    id_column = "escalation_id"

    @staticmethod
    def _now_iso():
        return datetime.now(UTC).isoformat()

    def _generate_escalation_id(self):
        # UUIDs avoid count()+1 collisions when two dockets are escalated
        # concurrently; callers should treat this as an opaque identifier.
        return f"ESC-{uuid4().hex[:24].upper()}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("escalation_id"):
            payload["escalation_id"] = self._generate_escalation_id()
        if not payload.get("status"):
            payload["status"] = "OPEN"
        if not payload.get("created_at"):
            payload["created_at"] = self._now_iso()
        if not payload.get("updated_at"):
            payload["updated_at"] = self._now_iso()
        return super().create(payload)

    def list_by_case(self, case_reference):
        instances = self.model.query.filter_by(case_reference=case_reference).all()
        return [self._serialize(instance) for instance in instances]

    def list_unresolved(self):
        instances = self.session.query(self.model).filter(self.model.status.in_(["OPEN", "UNDER_REVIEW"])).all()
        return [self._serialize(instance) for instance in instances]

    def get_unresolved_for_case(self, case_reference):
        instances = (
            self.session.query(self.model)
            .filter(
                self.model.case_reference == case_reference,
                self.model.status.in_(["OPEN", "UNDER_REVIEW"]),
            )
            .order_by(self.model.id.asc())
            .all()
        )
        return self._serialize(instances[0]) if instances else None

    def list_open(self):
        instances = self.model.query.filter_by(status="OPEN").all()
        return [self._serialize(instance) for instance in instances]

    def list_by_status(self, status):
        target = str(status or "").upper()
        instances = self.model.query.filter_by(status=target).all()
        return [self._serialize(instance) for instance in instances]

    def update_status(self, escalation_id, new_status):
        instance = self.model.query.filter_by(escalation_id=escalation_id).first()
        if instance is None:
            return None
        instance.status = str(new_status or "").upper()
        instance.updated_at = self._now_iso()
        self._commit()
        return self._serialize(instance)

    def update(self, escalation_id, payload):
        payload = dict(payload)
        if not payload.get("updated_at"):
            payload["updated_at"] = self._now_iso()
        return super().update(escalation_id, payload)
