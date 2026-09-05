"""Repository boundary for detective investigation findings."""

from app.database.repositories.base_repository import InMemoryRepository


class InvestigationFindingRepository(InMemoryRepository):
    """In-memory persistence for investigation findings."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    def create(self, payload):
        item = dict(payload)
        item.setdefault("id", len(self._items) + 1)
        item.setdefault("finding_id", f"FND-{len(self._items) + 1:06d}")
        self._items.append(item)
        return dict(item)

    def list_for_investigation(self, investigation_id):
        return [dict(item) for item in self._items if item.get("investigation_id") == investigation_id]

    def list_for_case(self, case_reference):
        return [dict(item) for item in self._items if item.get("case_reference") == case_reference]

    def get_for_finding_id(self, finding_id):
        for item in self._items:
            if item.get("finding_id") == finding_id:
                return dict(item)
        return None
