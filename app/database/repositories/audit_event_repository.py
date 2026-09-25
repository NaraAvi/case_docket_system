"""Repository boundary for the persistent, append-only audit trail."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import AuditEvent


class AuditEventRepository(BaseSqlAlchemyRepository):
    """Persistence for audit events. Append-only: update and delete are refused."""

    model = AuditEvent
    id_column = "event_id"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _generate_event_id(self):
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"AUDIT-{sequence:06d}"

    def _serialize(self, instance):
        data = super()._serialize(instance)
        if data is None:
            return None
        if "metadata" not in data and "metadata_json" in data:
            data["metadata"] = data.pop("metadata_json", {})
        if "details" not in data and "details_json" in data:
            data["details"] = data.pop("details_json", {})
        return data

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("event_id"):
            payload["event_id"] = self._generate_event_id()
        if not payload.get("timestamp"):
            payload["timestamp"] = self._utc_now()
        if "metadata" in payload:
            payload["metadata_json"] = payload.pop("metadata")
        if "details" in payload:
            payload["details_json"] = payload.pop("details")
        return super().create(payload)

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_actor(self, actor_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(actor_id=str(actor_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def update(self, identifier, payload):
        raise ValueError("Audit event history is immutable and append-only.")

    def delete(self, identifier):
        raise ValueError("Audit event history is immutable and append-only.")
