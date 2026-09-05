"""Repository boundary for docket assignment lifecycle state."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import InMemoryRepository


class AssignmentRepository(InMemoryRepository):
    """In-memory persistence for assignment records and historical state."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _generate_assignment_id(sequence):
        return f"ASG-{sequence:06d}"

    def create(self, payload):
        item = dict(payload)
        item.setdefault("assignment_id", self._generate_assignment_id(len(self._items) + 1))
        item.setdefault("status", "ACTIVE")
        item.setdefault("assigned_at", self._utc_now())
        self._items.append(item)
        return dict(item)

    def get_by_id(self, assignment_id):
        for item in self._items:
            if item.get("assignment_id") == assignment_id:
                return dict(item)
        return None

    def get_current_assignment_for_case(self, case_reference):
        matches = [
            dict(item)
            for item in self._items
            if item.get("case_reference") == case_reference and item.get("status") == "ACTIVE"
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: str(item.get("assigned_at") or ""), reverse=True)
        return matches[0]

    def get_history_for_case(self, case_reference):
        matches = [
            dict(item)
            for item in self._items
            if item.get("case_reference") == case_reference
        ]
        matches.sort(key=lambda item: str(item.get("assigned_at") or ""))
        return matches

    def query_by_officer(self, officer_id):
        return [
            dict(item)
            for item in self._items
            if item.get("officer_id") == officer_id
        ]

    def end_assignment(self, assignment_id, ended_by=None, ended_by_role=None, reason=None):
        for index, item in enumerate(self._items):
            if item.get("assignment_id") == assignment_id:
                record = dict(item)
                record["status"] = "ENDED"
                record["ended_at"] = self._utc_now()
                record["ended_by"] = ended_by
                record["ended_by_role"] = ended_by_role
                record["end_reason"] = reason
                self._items[index] = record
                return dict(record)
        return None
