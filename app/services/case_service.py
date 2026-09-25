"""Case lifecycle orchestration for citizen docket creation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.database.repositories.case_repository import CaseRepository


def new_evidence_id():
    """Return a globally unique, URL-safe evidence identifier."""
    return f"EVD-{uuid4().hex}"


class CaseService:
    """Application service to manage docket lifecycle orchestration."""

    def __init__(self, repository=None):
        self.repository = repository or CaseRepository()

    @staticmethod
    def generate_case_reference(index):
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        return f"CD-{stamp}-{index:06d}"

    @staticmethod
    def _timeline_event(event_type, actor_id, actor_role, details=None):
        return {
            "event_type": event_type,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "timestamp": datetime.now(UTC).isoformat(),
            "details": details or {},
        }

    def create_case(self, citizen_id, case_data):
        if not citizen_id:
            raise ValueError("Citizen is required to create a case.")

        next_index = len(self.repository.list()) + 1
        case_payload = {
            **case_data,
            "id": next_index,
            "citizen_id": citizen_id,
            "case_reference": self.generate_case_reference(next_index),
            "status": "DRAFT",
            "statements": [],
            "evidence": [],
            "timeline": [
                self._timeline_event(
                    "docket_created",
                    citizen_id,
                    "citizen",
                    {"status": "DRAFT"},
                )
            ],
        }
        return self.repository.create(case_payload)

    def update_case(self, case_data):
        case_id = case_data.get("id")
        if case_id is None:
            raise ValueError("Case identifier is required to update a case.")
        updated = self.repository.update(case_id, case_data)
        return updated

    def list_cases_for_citizen(self, citizen_id):
        return self.repository.list_for_citizen(citizen_id)

    def get_case_for_citizen(self, citizen_id, case_reference):
        return self.repository.get_for_citizen(citizen_id, case_reference)

    def get_all_cases(self):
        return self.repository.list()
