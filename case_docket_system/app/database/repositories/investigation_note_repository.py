"""Repository boundary for multi-entry detective investigation notes."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import InvestigationNote


class InvestigationNoteRepository(BaseSqlAlchemyRepository):
    """Persistence for append-only investigation note entries."""

    model = InvestigationNote
    id_column = "note_id"

    def _generate_note_id(self):
        sequence = self.model.query.count() + 1
        return f"NOTE-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("note_id"):
            payload["note_id"] = self._generate_note_id()
        return super().create(payload)

    def list_for_investigation(self, investigation_id):
        instances = self.model.query.filter_by(investigation_id=investigation_id).all()
        return [self._serialize(instance) for instance in instances]
