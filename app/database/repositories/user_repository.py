"""Repository boundary for persistent user/identity records."""

from __future__ import annotations

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import User


class UserRepository(BaseSqlAlchemyRepository):
    """Persistence for the users table, keyed by test_id."""

    model = User
    id_column = "test_id"

    def list_by_role(self, role):
        instances = self.model.query.filter_by(role=role).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def seed_if_empty(self, identities):
        """Idempotently seed synthetic test identities. No-op if the table has rows."""
        if self.model.query.count() > 0:
            return False

        for identity in identities:
            payload = {
                "test_id": identity["test_id"],
                "full_name": identity["full_name"],
                "role": identity["role"],
                "active": bool(identity.get("active", True)),
                "access_state": "ACTIVE",
                "source": identity.get("source", "development_test"),
            }
            data = self._filter_payload(payload)
            self.session.add(self.model(**data))
        self._commit()
        return True
