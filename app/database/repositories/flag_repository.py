"""Repository boundary for constable invalidity flags."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import Flag


class FlagRepository(BaseSqlAlchemyRepository):
    """Persistence for case review flags."""

    model = Flag
    id_column = "flag_id"

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_flag_id(self, flag_id):
        return self.get_by_id(flag_id)
