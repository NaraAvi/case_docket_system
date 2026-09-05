"""Case repository for foundational citizen docket persistence."""

from app.database.repositories.base_repository import InMemoryRepository


class CaseRepository(InMemoryRepository):
    """Repository boundary for case-related persistence."""

    _shared_sequence = 1

    def __init__(self, session=None):
        super().__init__(session=session)
        self._sequence = self.__class__._shared_sequence

    def create(self, payload):
        item = dict(payload)
        item.setdefault("id", self._sequence)
        self._sequence += 1
        self.__class__._shared_sequence = self._sequence
        self._items.append(item)
        return dict(item)

    def list_for_citizen(self, citizen_id):
        return [dict(item) for item in self._items if item.get("citizen_id") == citizen_id]

    def get_for_citizen(self, citizen_id, case_reference):
        for item in self._items:
            if item.get("citizen_id") == citizen_id and item.get("case_reference") == case_reference:
                return dict(item)
        return None
