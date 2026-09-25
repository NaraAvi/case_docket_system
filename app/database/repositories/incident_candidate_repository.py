from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import IncidentCandidate, Relationship


class IncidentCandidateRepository(BaseSqlAlchemyRepository):
    model = IncidentCandidate
    id_column = "candidate_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).all()
        matches = []
        for instance in instances:
            source_ids = instance.source_submission_ids or []
            if str(submission_id) in {str(item) for item in source_ids}:
                matches.append(self._serialize(instance))
        return matches

    def list_for_citizen(self, citizen_id):
        with self._app_context():
            instances = self.session.query(self.model).all()
        return [self._serialize(item) for item in instances if str(item.source_actor_id) == str(citizen_id)]

    def update(self, identifier, payload):
        if identifier is None or not isinstance(payload, dict):
            return None
        with self._app_context():
            instance = self.session.query(self.model).filter(self._lookup_column() == identifier).first()
            if instance is None:
                return None
            allowed_keys = {"status", "deterministic_basis", "explanation", "derivation_rule"}
            for key, value in payload.items():
                if key not in allowed_keys:
                    raise ValueError("Incident candidate history is provisional; only status and deterministic explanation fields may update.")
                setattr(instance, key, value)
            self.session.commit()
            return self._serialize(instance)

    def delete(self, identifier):
        raise ValueError("Incident candidate history cannot be deleted.")


class RelationshipRepository(BaseSqlAlchemyRepository):
    model = Relationship
    id_column = "relationship_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).all()
        matches = []
        for instance in instances:
            if str(instance.source_submission_id) == str(submission_id) or str(instance.related_submission_id) == str(submission_id):
                matches.append(self._serialize(instance))
        return matches

    def get_by_rule(self, source_submission_id, related_submission_id, relationship_type, rule_name):
        with self._app_context():
            instances = self.session.query(self.model).all()
        for instance in instances:
            if (
                str(instance.source_submission_id) == str(source_submission_id)
                and str(instance.related_submission_id) == str(related_submission_id)
                and str(instance.relationship_type) == str(relationship_type)
                and str(instance.rule_name) == str(rule_name)
            ):
                return self._serialize(instance)
        return None

    def update(self, identifier, payload):
        raise ValueError("Relationship derivations are append-only and cannot be overwritten.")

    def delete(self, identifier):
        raise ValueError("Relationship history cannot be deleted.")
