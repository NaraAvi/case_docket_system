"""Repository boundary for IPID escalation persistence."""

from __future__ import annotations

from datetime import UTC, datetime

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
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"ESC-{sequence:06d}"

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
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).all()
        return [self._serialize(instance) for instance in instances]

    def list_open(self):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(status="OPEN").all()
        return [self._serialize(instance) for instance in instances]

    def list_unresolved(self):
        """OPEN + UNDER_REVIEW -- everything not yet decided. Used as the
        default IPID queue view so an escalation doesn't disappear from the
        dashboard the moment a reviewer opens it (which transitions it from
        OPEN to UNDER_REVIEW) but before a decision has actually been made."""
        with self._app_context():
            instances = self.session.query(self.model).filter(self.model.status.in_(["OPEN", "UNDER_REVIEW"])).all()
        return [self._serialize(instance) for instance in instances]

    def list_by_status(self, status):
        target = str(status or "").upper()
        with self._app_context():
            instances = self.session.query(self.model).filter_by(status=target).all()
        return [self._serialize(instance) for instance in instances]

    def update_status(self, escalation_id, new_status):
        with self._app_context():
            instance = self.session.query(self.model).filter_by(escalation_id=escalation_id).first()
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
