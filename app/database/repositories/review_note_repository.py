"""Repository boundary for internal IPID review notes."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import InMemoryRepository


class ReviewNoteRepository(InMemoryRepository):
    """In-memory persistence for internal review notes."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def create(self, payload):
        item = dict(payload)
        item.setdefault("note_id", f"RNT-{len(self._items) + 1:06d}")
        item.setdefault("note_text", item.get("note") or item.get("note_text") or "")
        item.setdefault("created_at", self._utc_now())
        item.setdefault("updated_at", self._utc_now())
        self._items.append(item)
        return dict(item)

    def list_for_escalation(self, escalation_id):
        return [dict(item) for item in self._items if item.get("escalation_id") == escalation_id]

    def get_for_note_id(self, note_id):
        for item in self._items:
            if item.get("note_id") == note_id:
                return dict(item)
        return None
