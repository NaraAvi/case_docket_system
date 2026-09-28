"""Repository boundary for detective investigation actions."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import InvestigationAction


class InvestigationActionRepository(BaseSqlAlchemyRepository):
    """Persistence for append-only investigative actions."""

    model = InvestigationAction
    id_column = "action_id"

    def _generate_action_id(self):
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"ACT-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("action_id"):
            payload["action_id"] = self._generate_action_id()
        return super().create(payload)

    def list_for_investigation(self, investigation_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(investigation_id=investigation_id).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]
