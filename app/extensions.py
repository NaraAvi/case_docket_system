from contextlib import contextmanager

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_marshmallow import Marshmallow
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
jwt = JWTManager()
migrate = Migrate()
cors = CORS()
ma = Marshmallow()


@contextmanager
def unit_of_work():
    """Defer repository commits and commit/rollback one shared session.

    Domain services that span several repositories can use this boundary so a
    failed multi-table operation does not leave a partial state behind.
    """
    session = db.session()
    previous = session.info.get("defer_commit", False)
    if previous:
        yield session
        return

    session.info["defer_commit"] = True
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.info.pop("defer_commit", None)
