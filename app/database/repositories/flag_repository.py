"""Repository boundary for constable invalidity flags."""

from app.database.repositories.base_repository import InMemoryRepository


class FlagRepository(InMemoryRepository):
    """In-memory persistence for case review flags."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    def create(self, payload):
        item = dict(payload)
        item.setdefault("id", len(self._items) + 1)
        self._items.append(item)
        return dict(item)

    def update(self, identifier, payload):
        for index, item in enumerate(self._items):
            if item.get("id") == identifier or item.get("flag_id") == identifier:
                self._items[index] = dict(payload)
                return dict(payload)
        return None

    def list_for_case(self, case_reference):
        return [dict(item) for item in self._items if item.get("case_reference") == case_reference]

    def get_for_flag_id(self, flag_id):
        for item in self._items:
            if item.get("flag_id") == flag_id:
                return dict(item)
        return None
