"""Investigation repository for detective investigation records."""

from app.database.repositories.base_repository import InMemoryRepository


class InvestigationRepository(InMemoryRepository):
    """Repository boundary for investigation lifecycle records."""

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

    def get_by_investigation_id(self, investigation_id):
        for item in self._items:
            if item.get("investigation_id") == investigation_id:
                return dict(item)
        return None

    def list_for_case(self, case_reference):
        return [dict(item) for item in self._items if item.get("case_reference") == case_reference]

    def list_for_detective(self, detective_id):
        return [dict(item) for item in self._items if item.get("detective_id") == detective_id]
