"""Repository boundary for case freeze lifecycle state."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import InMemoryRepository


class FreezeRepository(InMemoryRepository):
    """In-memory persistence for active and historical freeze records."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _generate_freeze_id(sequence):
        return f"FRZ-{sequence:06d}"

    def create(self, payload):
        item = dict(payload)
        item.setdefault("freeze_id", self._generate_freeze_id(len(self._items) + 1))
        item.setdefault("status", "ACTIVE")
        item.setdefault("frozen_at", self._utc_now())
        self._items.append(item)
        return dict(item)

    def update(self, identifier, payload):
        for index, item in enumerate(self._items):
            if item.get("freeze_id") == identifier:
                updated = dict(payload)
                self._items[index] = updated
                return dict(updated)
        return None

    def get_by_id(self, freeze_id):
        for item in self._items:
            if item.get("freeze_id") == freeze_id:
                return dict(item)
        return None

    def get_history_for_case(self, case_reference):
        matches = [
            dict(item)
            for item in self._items
            if item.get("case_reference") == case_reference
        ]
        matches.sort(key=lambda item: str(item.get("frozen_at") or ""))
        return matches

    def get_current_for_case(self, case_reference):
        matches = [
            dict(item)
            for item in self._items
            if item.get("case_reference") == case_reference and item.get("status") == "ACTIVE"
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: str(item.get("frozen_at") or ""))
        return matches[-1]
