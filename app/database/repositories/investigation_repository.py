"""Investigation repository for detective investigation records."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import Investigation


class InvestigationRepository(BaseSqlAlchemyRepository):
    """Repository boundary for investigation lifecycle records."""

    model = Investigation

    def get_by_investigation_id(self, investigation_id):
        instance = self.model.query.filter_by(investigation_id=investigation_id).first()
        return self._serialize(instance)

    def list_for_case(self, case_reference):
        instances = self.model.query.filter_by(case_reference=case_reference).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_detective(self, detective_id):
        instances = self.model.query.filter_by(detective_id=detective_id).all()
        return [self._serialize(instance) for instance in instances]
