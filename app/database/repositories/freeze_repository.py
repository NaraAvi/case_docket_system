"""Repository boundary for case freeze lifecycle state."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import Freeze


class FreezeRepository(BaseSqlAlchemyRepository):
    """Persistence for active and historical freeze records."""

    model = Freeze
    id_column = "freeze_id"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _generate_freeze_id(self):
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"FRZ-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("freeze_id"):
            payload["freeze_id"] = self._generate_freeze_id()
        if not payload.get("status"):
            payload["status"] = "ACTIVE"
        if not payload.get("frozen_at"):
            payload["frozen_at"] = self._utc_now()
        return super().create(payload)

    def get_history_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).all()
        matches = [self._serialize(instance) for instance in instances]
        matches.sort(key=lambda item: str(item.get("frozen_at") or ""))
        return matches

    def get_current_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference, status="ACTIVE").all()
        matches = [self._serialize(instance) for instance in instances]
        if not matches:
            return None
        matches.sort(key=lambda item: str(item.get("frozen_at") or ""))
        return matches[-1]

    def list_active(self):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(status="ACTIVE").all()
        matches = [self._serialize(instance) for instance in instances]
        matches.sort(key=lambda item: str(item.get("frozen_at") or ""), reverse=True)
        return matches
