"""Repository boundary for citizen assertions and derived claims."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import Assertion, Claim


class AssertionRepository(BaseSqlAlchemyRepository):
    """Append-only repository for assertion records tied to a protected submission."""

    model = Assertion
    id_column = "assertion_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(submission_id=str(submission_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_citizen(self, citizen_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(citizen_id=str(citizen_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_submission(self, citizen_id, submission_id, assertion_id):
        with self._app_context():
            instance = self.session.query(self.model).filter_by(
                citizen_id=str(citizen_id),
                submission_id=str(submission_id),
                assertion_id=str(assertion_id),
            ).first()
        return self._serialize(instance)

    def update(self, identifier, payload):
        raise ValueError("Assertion content is immutable and append-only.")

    def delete(self, identifier):
        raise ValueError("Assertion history is immutable and cannot be deleted.")


class ClaimRepository(BaseSqlAlchemyRepository):
    """Append-only repository for normalized claims derived from assertions."""

    model = Claim
    id_column = "claim_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(submission_id=str(submission_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_assertion(self, assertion_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(assertion_id=str(assertion_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_assertion(self, citizen_id, submission_id, assertion_id, claim_id):
        with self._app_context():
            instance = self.session.query(self.model).filter_by(
                citizen_id=str(citizen_id),
                submission_id=str(submission_id),
                assertion_id=str(assertion_id),
                claim_id=str(claim_id),
            ).first()
        return self._serialize(instance)

    def update(self, identifier, payload):
        raise ValueError("Claim provenance and content are immutable after creation.")

    def delete(self, identifier):
        raise ValueError("Claim history is immutable and cannot be deleted.")
