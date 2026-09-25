"""Base repository contracts for persistence operations."""

from __future__ import annotations

from contextlib import contextmanager

from flask import has_app_context
from sqlalchemy import inspect as sa_inspect

from app.extensions import db


class BaseRepository:
    """Shared repository pattern placeholder."""

    def __init__(self, session=None, app=None):
        self._session = session
        self.app = app

    @property
    def session(self):
        if self._session is not None:
            return self._session
        return db.session

    @session.setter
    def session(self, value):
        self._session = value

    @contextmanager
    def _app_context(self):
        if has_app_context():
            yield
            return
        if self.app is not None:
            with self.app.app_context():
                yield
            return
        if self._session is not None:
            yield
            return
        raise RuntimeError("Working outside of application context.")

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

    The session is intentionally resolved lazily so repository instances can be
    created safely before a request/app context is active, while still using the
    active Flask app context when the operation actually executes.
    """

    model = None
    id_column = "id"

    def __init__(self, session=None, app=None):
        super().__init__(session=session, app=app)

    def _attribute_names(self):
        return {prop.key for prop in sa_inspect(self.model).column_attrs}

    def _filter_payload(self, payload):
        attributes = self._attribute_names()
        alias_targets = {
            "metadata": "metadata_json",
            "details": "details_json",
        }
        filtered = {}
        for key, value in payload.items():
            if key in attributes:
                filtered[key] = value
                continue
            target = alias_targets.get(key)
            if target and target in attributes:
                filtered[target] = value
        return filtered

    def _serialize(self, instance):
        if instance is None:
            return None
        data = {}
        for name in self._attribute_names():
            value = getattr(instance, name)
            translated_name = name.removesuffix("_json") if name.endswith("_json") and name.removesuffix("_json") in {"metadata", "details"} else name
            data[translated_name] = value
        return data

    def _lookup_column(self):
        return getattr(self.model, self.id_column)

    def _commit(self):
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def get_by_id(self, identifier):
        if identifier is None:
            return None
        with self._app_context():
            instance = self.session.query(self.model).filter(self._lookup_column() == identifier).first()
            return self._serialize(instance)

    def list_all(self):
        with self._app_context():
            instances = self.session.query(self.model).order_by(self.model.id.asc()).all()
            return [self._serialize(instance) for instance in instances]

    # Preserved for compatibility with the original in-memory repositories,
    # whose `list()` method is called throughout the service layer.
    list = list_all

    def create(self, payload):
        with self._app_context():
            data = self._filter_payload(payload)
            instance = self.model(**data)
            self.session.add(instance)
            self._commit()
            return self._serialize(instance)

    def update(self, identifier, payload):
        if identifier is None:
            return None
        with self._app_context():
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
        with self._app_context():
            instance = self.session.query(self.model).filter(self._lookup_column() == identifier).first()
            if instance is None:
                return None
            serialized = self._serialize(instance)
            self.session.delete(instance)
            self._commit()
            return serialized

    def paginate(self, page=1, per_page=20):
        with self._app_context():
            query = self.session.query(self.model).order_by(self.model.id.asc())
            total = query.count()
            items = query.offset((page - 1) * per_page).limit(per_page).all()
            return {
                "items": [self._serialize(instance) for instance in items],
                "page": page,
                "per_page": per_page,
                "total": total,
            }
