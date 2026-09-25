"""Repository boundary for declared conflicts of interest (Milestone 4.4)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import ConflictDeclaration


class ConflictDeclarationRepository(BaseSqlAlchemyRepository):
    """Persistence for conflict-of-interest declarations."""

    model = ConflictDeclaration
    id_column = "declaration_id"

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _generate_declaration_id(self):
        with self._app_context():
            sequence = self.session.query(self.model).count() + 1
        return f"COI-{sequence:06d}"

    def create(self, payload):
        payload = dict(payload)
        if not payload.get("declaration_id"):
            payload["declaration_id"] = self._generate_declaration_id()
        if not payload.get("status"):
            payload["status"] = "ACTIVE"
        if not payload.get("declared_at"):
            payload["declared_at"] = self._utc_now()
        return super().create(payload)

    def list_active_for_officer(self, officer_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(officer_id=str(officer_id), status="ACTIVE").all()
        return [self._serialize(instance) for instance in instances]

    def list_for_officer(self, officer_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(officer_id=str(officer_id)).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]
