"""Base repository contracts for persistence operations."""

from __future__ import annotations

from sqlalchemy import inspect as sa_inspect

from app.extensions import db


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


class BaseSqlAlchemyRepository(BaseRepository):
    """Generic CRUD repository backed by a SQLAlchemy model and db.session.

    Subclasses set `model` (a db.Model) and, when the natural lookup key isn't
    the surrogate primary key, `id_column` (the column name used by
    get_by_id/update/delete/paginate lookups).
    """

    model = None
    id_column = "id"

    def __init__(self, session=None):
        super().__init__(session=session or db.session)

    def _attribute_names(self):
        return {prop.key for prop in sa_inspect(self.model).column_attrs}

    def _filter_payload(self, payload):
        attributes = self._attribute_names()
        return {key: value for key, value in payload.items() if key in attributes}

    def _serialize(self, instance):
        if instance is None:
            return None
        return {name: getattr(instance, name) for name in self._attribute_names()}

    def _lookup_column(self):
        return getattr(self.model, self.id_column)

    def _session_instance(self):
        # Repositories normally hold Flask-SQLAlchemy's scoped_session proxy,
        # while tests/integrations may inject a real Session instance.
        return self.session() if callable(self.session) else self.session

    def _commit(self):
        session = self._session_instance()
        if getattr(session, "info", {}).get("defer_commit"):
            return
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise

    def get_by_id(self, identifier):
        if identifier is None:
            return None
        instance = self.session.query(self.model).filter(self._lookup_column() == identifier).first()
        return self._serialize(instance)

    def list_all(self):
        instances = self.session.query(self.model).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    # Preserved for compatibility with the original in-memory repositories,
    # whose `list()` method is called throughout the service layer.
    list = list_all

    def create(self, payload):
        data = self._filter_payload(payload)
        instance = self.model(**data)
        self.session.add(instance)
        self._commit()
        return self._serialize(instance)

    def update(self, identifier, payload):
        if identifier is None:
            return None
        instance = self.session.query(self.model).filter(self._lookup_column() == identifier).first()
        if instance is None:
            return None
        data = self._filter_payload(payload)
        for key, value in data.items():
            setattr(instance, key, value)
        self._commit()
        return self._serialize(instance)

    def delete(self, identifier):
        if identifier is None:
            return None
        instance = self.session.query(self.model).filter(self._lookup_column() == identifier).first()
        if instance is None:
            return None
        serialized = self._serialize(instance)
        self.session.delete(instance)
        self._commit()
        return serialized

    def paginate(self, page=1, per_page=20):
        query = self.session.query(self.model).order_by(self.model.id.asc())
        total = query.count()
        items = query.offset((page - 1) * per_page).limit(per_page).all()
        return {
            "items": [self._serialize(instance) for instance in items],
            "page": page,
            "per_page": per_page,
            "total": total,
        }
