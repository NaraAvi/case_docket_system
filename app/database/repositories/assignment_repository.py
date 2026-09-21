"""Repository boundary for docket assignment lifecycle state."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import Assignment


class AssignmentRepository(BaseSqlAlchemyRepository):
    """Persistence for assignment records and historical state."""

    model = Assignment
    id_column = "assignment_id"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _generate_assignment_id(self):
        sequence = self.model.query.count() + 1
        return f"ASG-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("assignment_id"):
            payload["assignment_id"] = self._generate_assignment_id()
        if not payload.get("status"):
            payload["status"] = "ACTIVE"
        if not payload.get("assigned_at"):
            payload["assigned_at"] = self._utc_now()
        return super().create(payload)

    def get_current_assignment_for_case(self, case_reference):
        instances = self.model.query.filter_by(case_reference=case_reference, status="ACTIVE").all()
        matches = [self._serialize(instance) for instance in instances]
        if not matches:
            return None
        matches.sort(key=lambda item: str(item.get("assigned_at") or ""), reverse=True)
        return matches[0]

    def get_history_for_case(self, case_reference):
        instances = self.model.query.filter_by(case_reference=case_reference).all()
        matches = [self._serialize(instance) for instance in instances]
        matches.sort(key=lambda item: str(item.get("assigned_at") or ""))
        return matches

    def query_by_officer(self, officer_id):
        instances = self.model.query.filter_by(officer_id=officer_id).all()
        return [self._serialize(instance) for instance in instances]

    def end_assignment(self, assignment_id, ended_by=None, ended_by_role=None, reason=None):
        instance = self.model.query.filter_by(assignment_id=assignment_id).first()
        if instance is None:
            return None
        instance.status = "ENDED"
        instance.ended_at = self._utc_now()
        instance.ended_by = ended_by
        instance.ended_by_role = ended_by_role
        instance.end_reason = reason
        self._commit()
        return self._serialize(instance)

    def list_suspended_for_case(self, case_reference):
        instances = self.model.query.filter_by(case_reference=case_reference, status="SUSPENDED").all()
        matches = [self._serialize(instance) for instance in instances]
        matches.sort(key=lambda item: str(item.get("assigned_at") or ""))
        return matches

    def suspend_assignment(self, assignment_id, suspended_by=None, reason=None):
        instance = self.model.query.filter_by(assignment_id=assignment_id, status="ACTIVE").first()
        if instance is None:
            return None
        instance.status = "SUSPENDED"
        instance.suspended_at = self._utc_now()
        instance.suspended_by = suspended_by
        instance.suspension_reason = reason
        self._commit()
        return self._serialize(instance)

    def reinstate_assignment(self, assignment_id):
        instance = self.model.query.filter_by(assignment_id=assignment_id, status="SUSPENDED").first()
        if instance is None:
            return None
        instance.status = "ACTIVE"
        instance.suspended_at = None
        instance.suspended_by = None
        instance.suspension_reason = None
        self._commit()
        return self._serialize(instance)
