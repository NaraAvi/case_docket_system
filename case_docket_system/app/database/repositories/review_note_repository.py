"""Repository boundary for internal IPID review notes."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import ReviewNote


class ReviewNoteRepository(BaseSqlAlchemyRepository):
    """Persistence for internal review notes."""

    model = ReviewNote
    id_column = "note_id"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _generate_note_id(self):
        sequence = self.model.query.count() + 1
        return f"RNT-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("note_id"):
            payload["note_id"] = self._generate_note_id()
        if not payload.get("note_text"):
            payload["note_text"] = payload.get("note") or payload.get("note_text") or ""
        if not payload.get("created_at"):
            payload["created_at"] = self._utc_now()
        if not payload.get("updated_at"):
            payload["updated_at"] = self._utc_now()
        return super().create(payload)

    def list_for_escalation(self, escalation_id):
        instances = self.model.query.filter_by(escalation_id=escalation_id).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_note_id(self, note_id):
        return self.get_by_id(note_id)
