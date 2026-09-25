"""Repository boundary for disciplinary case persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import DisciplinaryCase


class DisciplinaryCaseRepository(BaseSqlAlchemyRepository):
    """Persistence for disciplinary case records."""

    model = DisciplinaryCase
    id_column = "disciplinary_case_id"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _generate_case_id(self):
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"DIC-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("disciplinary_case_id"):
            payload["disciplinary_case_id"] = self._generate_case_id()
        if not payload.get("status"):
            payload["status"] = "OPEN"
        if not payload.get("category"):
            payload["category"] = "OFFICER_CONDUCT"
        if not payload.get("created_at"):
            payload["created_at"] = self._utc_now()
        if not payload.get("updated_at"):
            payload["updated_at"] = self._utc_now()
        return super().create(payload)

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(source_case_reference=case_reference).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_escalation(self, escalation_id):
        if escalation_id is None:
            return None
        with self._app_context():
            instance = self.session.query(self.model).filter_by(escalation_id=str(escalation_id)).first()
        return self._serialize(instance)

    def list_for_officer(self, officer_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(implicated_officer_id=str(officer_id)).all()
        return [self._serialize(instance) for instance in instances]
