from logging.config import fileConfig
from pathlib import Path

from alembic import context
from flask import current_app
from sqlalchemy import engine_from_config, inspect, pool, text
from sqlalchemy.engine import make_url

from app import create_app
from app.extensions import db

# this is the Alembic Config object, which provides access to the
# values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# this is the target metadata for 'autogenerate' support.
# target_metadata = mymodel.Base.metadata
raw_database_url = current_app.config.get("SQLALCHEMY_DATABASE_URI")
database_url = make_url(raw_database_url)
if (
    database_url.drivername == "sqlite"
    and database_url.database
    and database_url.database != ":memory:"
    and not Path(database_url.database).is_absolute()
):
    # Flask-SQLAlchemy resolves relative SQLite paths under instance_path;
    # Alembic's engine_from_config otherwise resolves them from the process CWD.
    normalized_database_url = "sqlite:///" + (
        Path(current_app.instance_path) / database_url.database
    ).as_posix()
else:
    normalized_database_url = raw_database_url
config.set_main_option("sqlalchemy.url", normalized_database_url)

target_metadata = db.metadata
INITIAL_REVISION = "84d740a5539c"


def _stamp_schema_created_by_create_all(connection):
    """Recognize a development DB initialized by ``db.create_all``.

    The legacy app factory creates tables before Flask-Migrate is invoked. If
    the complete initial schema is already present but Alembic has no version
    row, mark the initial revision instead of trying to create those tables a
    second time. A partially-created database is left for Alembic to report.
    """
    inspector = inspect(connection)
    required_tables = {
        "assignments",
        "audit_events",
        "case_dockets",
        "disciplinary_cases",
        "evidence_index",
        "escalations",
        "flags",
        "freezes",
        "integrity_events",
        "interviews",
        "investigations",
        "investigation_findings",
        "recordings",
        "related_cases",
        "review_findings",
        "review_notes",
        "users",
    }
    if not required_tables.issubset(set(inspector.get_table_names())):
        return

    if not inspector.has_table("alembic_version"):
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    current = connection.execute(text("SELECT version_num FROM alembic_version")).first()
    if current is None:
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"), {"revision": INITIAL_REVISION})
        connection.commit()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    app = create_app()
    with app.app_context():
        connectable = engine_from_config(
            config.get_section(config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            _stamp_schema_created_by_create_all(connection)
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
            # SQLite DDL is non-transactional, so Alembic's context
            # transaction is a no-op there. Any implicit transaction opened
            # inside a migration (for example a SELECT used for a data
            # preflight) would otherwise be discarded when the connection
            # closes, silently losing both DDL and the version row.
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
