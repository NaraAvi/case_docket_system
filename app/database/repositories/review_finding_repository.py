"""Repository boundary for internal IPID review findings."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import ReviewFinding


class ReviewFindingRepository(BaseSqlAlchemyRepository):
    """Persistence for review findings."""

    model = ReviewFinding
    id_column = "finding_id"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _generate_finding_id(self):
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"RFG-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("finding_id"):
            payload["finding_id"] = self._generate_finding_id()
        if not payload.get("finding_type"):
            payload["finding_type"] = payload.get("type") or "FURTHER_REVIEW_REQUIRED"
        if not payload.get("summary"):
            payload["summary"] = payload.get("summary") or ""
        if not payload.get("created_at"):
            payload["created_at"] = self._utc_now()
        if not payload.get("updated_at"):
            payload["updated_at"] = self._utc_now()
        return super().create(payload)

    def list_for_escalation(self, escalation_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(escalation_id=escalation_id).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_finding_id(self, finding_id):
        return self.get_by_id(finding_id)
