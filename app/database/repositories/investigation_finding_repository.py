"""Repository boundary for detective investigation findings."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import InvestigationFinding


class InvestigationFindingRepository(BaseSqlAlchemyRepository):
    """Persistence for investigation findings."""

    model = InvestigationFinding
    id_column = "finding_id"

    def _generate_finding_id(self):
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"FND-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("finding_id"):
            payload["finding_id"] = self._generate_finding_id()
        return super().create(payload)

    def list_for_investigation(self, investigation_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(investigation_id=investigation_id).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_finding_id(self, finding_id):
        return self.get_by_id(finding_id)

    def update(self, identifier, payload):
        raise ValueError("Finding history is immutable and cannot be silently overwritten.")

    def delete(self, identifier):
        raise ValueError("Finding history is immutable and cannot be deleted.")
