"""Repository boundary for IPID escalation persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.base_repository import InMemoryRepository


class EscalationRepository(InMemoryRepository):
    """In-memory persistence for escalation records."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    @staticmethod
    def _now_iso():
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _generate_escalation_id(sequence):
        return f"ESC-{sequence:06d}"

    def create(self, payload):
        item = dict(payload)
        item.setdefault("escalation_id", self._generate_escalation_id(len(self._items) + 1))
        item.setdefault("status", "OPEN")
        item.setdefault("created_at", self._now_iso())
        item.setdefault("updated_at", self._now_iso())
        self._items.append(item)
        return dict(item)

    def get_by_id(self, escalation_id):
        for item in self._items:
            if item.get("escalation_id") == escalation_id:
                return dict(item)
        return None

    def list_by_case(self, case_reference):
        return [dict(item) for item in self._items if item.get("case_reference") == case_reference]

    def list_open(self):
        return [dict(item) for item in self._items if str(item.get("status") or "").upper() == "OPEN"]

    def list_by_status(self, status):
        target = str(status or "").upper()
        return [dict(item) for item in self._items if str(item.get("status") or "").upper() == target]

    def update_status(self, escalation_id, new_status):
        for index, item in enumerate(self._items):
            if item.get("escalation_id") == escalation_id:
                updated = dict(item)
                updated["status"] = str(new_status or "").upper()
                updated["updated_at"] = self._now_iso()
                self._items[index] = updated
                return dict(updated)
        return None

    def update(self, escalation_id, payload):
        for index, item in enumerate(self._items):
            if item.get("escalation_id") == escalation_id:
                updated = dict(payload)
                updated.setdefault("updated_at", self._now_iso())
                self._items[index] = updated
                return dict(updated)
        return None
