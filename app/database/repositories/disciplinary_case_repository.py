"""Repository boundary for disciplinary case persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import InMemoryRepository


class DisciplinaryCaseRepository(InMemoryRepository):
    """In-memory persistence for disciplinary case records."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _generate_case_id(sequence):
        return f"DIC-{sequence:06d}"

    def create(self, payload):
        item = dict(payload)
        item.setdefault("disciplinary_case_id", self._generate_case_id(len(self._items) + 1))
        item.setdefault("status", "OPEN")
        item.setdefault("category", "OFFICER_CONDUCT")
        item.setdefault("created_at", self._utc_now())
        item.setdefault("updated_at", self._utc_now())
        self._items.append(item)
        return dict(item)

    def get_by_id(self, disciplinary_case_id):
        for item in self._items:
            if item.get("disciplinary_case_id") == disciplinary_case_id:
                return dict(item)
        return None

    def list_for_case(self, case_reference):
        return [dict(item) for item in self._items if item.get("source_case_reference") == case_reference]
