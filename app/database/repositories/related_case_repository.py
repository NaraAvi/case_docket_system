"""Repository boundary for constable-related docket relationships."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import RelatedCase


class RelatedCaseRepository(BaseSqlAlchemyRepository):
    """Persistence for explicit docket-to-docket relationships."""

    model = RelatedCase
    id_column = "relationship_id"

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter(
                (self.model.source_case_reference == case_reference)
                | (self.model.related_case_reference == case_reference)
            ).all()
        return [self._serialize(instance) for instance in instances]

    def get_duplicate_relationship(self, source_case_reference, related_case_reference):
        source = str(source_case_reference)
        related = str(related_case_reference)
        if source == related:
            return None
        with self._app_context():
            instance = self.session.query(self.model).filter(
                (
                    (self.model.source_case_reference == source)
                    & (self.model.related_case_reference == related)
                )
                | (
                    (self.model.source_case_reference == related)
                    & (self.model.related_case_reference == source)
                )
            ).first()
        return self._serialize(instance)
