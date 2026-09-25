"""Repository boundary for protected citizen submissions."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import (
    ControlEvaluation,
    RuleEvaluation,
    Submission,
    SubmissionCorrection,
    SubmissionEvent,
    SubmissionEvidence,
    WithdrawalRequest,
)


class SubmissionRepository(BaseSqlAlchemyRepository):
    """Append-only repository for the submission boundary."""

    model = Submission
    id_column = "submission_id"

    def list_for_citizen(self, citizen_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(citizen_id=str(citizen_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_citizen(self, citizen_id, submission_id):
        with self._app_context():
            instance = self.session.query(self.model).filter_by(citizen_id=str(citizen_id), submission_id=str(submission_id)).first()
        return self._serialize(instance)

    def update(self, identifier, payload):
        raise ValueError("Submission content is immutable. Create a new submission for corrections.")

    def delete(self, identifier):
        raise ValueError("Submission content is immutable and cannot be removed.")


class SubmissionEventRepository(BaseSqlAlchemyRepository):
    """Repository for append-only event history entries."""

    model = SubmissionEvent
    id_column = "event_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(submission_id=str(submission_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def update(self, identifier, payload):
        raise ValueError("Submission event history is immutable and append-only.")

    def delete(self, identifier):
        raise ValueError("Submission event history is immutable and append-only.")


class RuleEvaluationRepository(BaseSqlAlchemyRepository):
    model = RuleEvaluation
    id_column = "evaluation_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(related_submission_id=str(submission_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_candidate(self, candidate_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(related_candidate_id=str(candidate_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def update(self, identifier, payload):
        raise ValueError("Rule evaluation history is immutable and append-only.")

    def delete(self, identifier):
        raise ValueError("Rule evaluation history cannot be removed.")


class ControlEvaluationRepository(BaseSqlAlchemyRepository):
    model = ControlEvaluation
    id_column = "control_evaluation_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(source_submission_id=str(submission_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_candidate(self, candidate_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(source_candidate_id=str(candidate_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def update(self, identifier, payload):
        raise ValueError("Control evaluation history is immutable and append-only.")

    def delete(self, identifier):
        raise ValueError("Control evaluation history cannot be removed.")


class SubmissionEvidenceRepository(BaseSqlAlchemyRepository):
    model = SubmissionEvidence
    id_column = "evidence_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(submission_id=str(submission_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def get_for_submission(self, citizen_id, submission_id, evidence_id):
        with self._app_context():
            instance = self.session.query(self.model).filter_by(
                citizen_id=str(citizen_id),
                submission_id=str(submission_id),
                evidence_id=str(evidence_id),
            ).first()
        return self._serialize(instance)

    def update(self, identifier, payload):
        raise ValueError("Evidence history is protected and versioned; replacements create a new handling record.")

    def delete(self, identifier):
        raise ValueError("Evidence is protected and cannot be destructively deleted.")


class SubmissionCorrectionRepository(BaseSqlAlchemyRepository):
    model = SubmissionCorrection
    id_column = "correction_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(submission_id=str(submission_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def update(self, identifier, payload):
        raise ValueError("Correction history is append-only and cannot be overwritten.")

    def delete(self, identifier):
        raise ValueError("Correction history cannot be deleted.")


class WithdrawalRequestRepository(BaseSqlAlchemyRepository):
    model = WithdrawalRequest
    id_column = "withdrawal_id"

    def list_for_submission(self, submission_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(submission_id=str(submission_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def update(self, identifier, payload):
        raise ValueError("Withdrawal requests are append-only and must preserve the original request.")

    def delete(self, identifier):
        raise ValueError("Withdrawal history cannot be deleted.")
