"""Repository boundary for internal IPID review findings."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import InMemoryRepository


class ReviewFindingRepository(InMemoryRepository):
    """In-memory persistence for review findings."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def create(self, payload):
        item = dict(payload)
        item.setdefault("finding_id", f"RFG-{len(self._items) + 1:06d}")
        item.setdefault("finding_type", item.get("type") or item.get("finding_type") or "FURTHER_REVIEW_REQUIRED")
        item.setdefault("summary", item.get("summary") or "")
        item.setdefault("created_at", self._utc_now())
        item.setdefault("updated_at", self._utc_now())
        self._items.append(item)
        return dict(item)

    def list_for_escalation(self, escalation_id):
        return [dict(item) for item in self._items if item.get("escalation_id") == escalation_id]

    def get_for_finding_id(self, finding_id):
        for item in self._items:
            if item.get("finding_id") == finding_id:
                return dict(item)
        return None
