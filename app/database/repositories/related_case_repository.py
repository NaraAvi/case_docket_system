"""Repository boundary for constable-related docket relationships."""

from app.database.repositories.base_repository import InMemoryRepository


class RelatedCaseRepository(InMemoryRepository):
    """In-memory persistence for explicit docket-to-docket relationships."""

    _shared_items = []

    def __init__(self, session=None):
        super().__init__(session=session)
        self._items = self.__class__._shared_items

    def create(self, payload):
        item = dict(payload)
        item.setdefault("id", len(self._items) + 1)
        self._items.append(item)
        return dict(item)

    def list_for_case(self, case_reference):
        return [
            dict(item)
            for item in self._items
            if item.get("source_case_reference") == case_reference
            or item.get("related_case_reference") == case_reference
        ]

    def get_duplicate_relationship(self, source_case_reference, related_case_reference):
        source = str(source_case_reference)
        related = str(related_case_reference)
        if source == related:
            return None
        for item in self._items:
            left = str(item.get("source_case_reference"))
            right = str(item.get("related_case_reference"))
            if (left == source and right == related) or (left == related and right == source):
                return dict(item)
        return None
