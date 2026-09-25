"""Case repository for foundational citizen docket persistence."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import CaseDocket


class CaseRepository(BaseSqlAlchemyRepository):
    """Repository boundary for case-related persistence."""

    model = CaseDocket

    def list_for_citizen(self, citizen_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(citizen_id=citizen_id).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_citizen(self, citizen_id, case_reference):
        with self._app_context():
            instance = self.session.query(self.model).filter_by(citizen_id=citizen_id, case_reference=case_reference).first()
        return self._serialize(instance)
