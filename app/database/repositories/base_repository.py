"""Base repository contract for persistence operations."""


class BaseRepository:
    """Shared repository pattern placeholder."""

    def __init__(self, session=None):
        self.session = session

    def list(self):
        raise NotImplementedError("Repository list operation not implemented yet.")

    def get(self, identifier):
        raise NotImplementedError("Repository get operation not implemented yet.")

    def create(self, payload):
        raise NotImplementedError("Repository create operation not implemented yet.")

    def update(self, identifier, payload):
        raise NotImplementedError("Repository update operation not implemented yet.")

    def delete(self, identifier):
        raise NotImplementedError("Repository delete operation not implemented yet.")


class InMemoryRepository(BaseRepository):
    """Minimal in-memory storage for Phase 2 workflow foundations."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    def list(self):
        return [dict(item) for item in self._items]

    def get(self, identifier):
        for item in self._items:
            if item.get("id") == identifier:
                return dict(item)
            if item.get("case_reference") == identifier:
                return dict(item)
        return None

    def create(self, payload):
        self._items.append(dict(payload))
        return dict(payload)

    def update(self, identifier, payload):
        for index, item in enumerate(self._items):
            if item.get("id") == identifier or item.get("case_reference") == identifier:
                self._items[index] = dict(payload)
                return dict(payload)
        return None

    def delete(self, identifier):
        for index, item in enumerate(self._items):
            if item.get("id") == identifier or item.get("case_reference") == identifier:
                return self._items.pop(index)
        return None
