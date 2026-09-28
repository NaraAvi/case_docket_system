"""Repository boundary for append-only accountability records."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import AccountabilityEvent, AccountabilityProfile


class AccountabilityProfileRepository(BaseSqlAlchemyRepository):
    """Persistent demerit profile keyed by the user identity it evaluates."""

    model = AccountabilityProfile
    id_column = "subject_id"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _generate_profile_id(self):
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"ACCT-PROFILE-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("profile_id"):
            payload["profile_id"] = self._generate_profile_id()
        if not payload.get("status"):
            payload["status"] = "NORMAL"
        if not payload.get("access_state"):
            payload["access_state"] = "ACTIVE"
        if not payload.get("created_at"):
            payload["created_at"] = self._utc_now()
        if not payload.get("updated_at"):
            payload["updated_at"] = self._utc_now()
        return super().create(payload)

    def get_for_subject(self, subject_id):
        return self.get_by_id(str(subject_id)) if subject_id is not None else None

    def list_review_required(self):
        with self._app_context():
            instances = self.session.query(self.model).filter(self.model.status.in_({"REVIEW_REQUIRED", "ACCOUNTABILITY_REVIEW", "FROZEN"})).all()
        return [self._serialize(instance) for instance in instances]


class AccountabilityEventRepository(BaseSqlAlchemyRepository):
    """Append-only accountability event history."""

    model = AccountabilityEvent
    id_column = "event_id"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _generate_event_id(self):
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"ACCT-EVT-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("event_id"):
            payload["event_id"] = self._generate_event_id()
        if not payload.get("created_at"):
            payload["created_at"] = self._utc_now()
        if "metadata" in payload and "metadata_json" not in payload:
            payload["metadata_json"] = payload.pop("metadata")
        return super().create(payload)

    def get_by_idempotency_key(self, idempotency_key):
        if not idempotency_key:
            return None
        with self._app_context():
            instance = self.session.query(self.model).filter_by(idempotency_key=str(idempotency_key)).first()
            return self._serialize(instance)

    def list_for_subject(self, subject_id):
        if subject_id is None:
            return []
        with self._app_context():
            instances = self.session.query(self.model).filter_by(subject_id=str(subject_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def update(self, identifier, payload):
        raise ValueError("Accountability event history is immutable and append-only.")

    def delete(self, identifier):
        raise ValueError("Accountability event history is immutable and append-only.")
