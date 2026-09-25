"""Prevent multiple unresolved escalations for one docket.

Revision ID: c7a1d4e9b2f6
Revises: 84d740a5539c
"""

from alembic import op
import sqlalchemy as sa


revision = "c7a1d4e9b2f6"
down_revision = "84d740a5539c"
branch_labels = None
depends_on = None


ACTIVE_STATUSES = "('OPEN', 'UNDER_REVIEW')"


def upgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            "SELECT case_reference, COUNT(*) AS active_count "
            "FROM escalations WHERE status IN ('OPEN', 'UNDER_REVIEW') "
            "GROUP BY case_reference HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if duplicate:
        refs = ", ".join(str(row[0]) for row in duplicate)
        raise RuntimeError(
            "Cannot enforce one unresolved escalation per docket; "
            f"reconcile active duplicates first: {refs}"
        )

    dialect = bind.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        raise RuntimeError(
            f"Unsupported database dialect {dialect!r}; the active escalation guard requires SQLite or PostgreSQL."
        )

    inspector = sa.inspect(bind)
    existing_checks = {item.get("name") for item in inspector.get_check_constraints("escalations")}
    if "ck_escalation_status" not in existing_checks:
        with op.batch_alter_table("escalations") as batch:
            batch.create_check_constraint(
                "ck_escalation_status",
                "status IN ('OPEN', 'UNDER_REVIEW', 'RESOLVED')",
            )

    inspector = sa.inspect(bind)
    existing_indexes = {item.get("name") for item in inspector.get_indexes("escalations")}
    if "uq_escalation_unresolved_case" not in existing_indexes:
        op.create_index(
            "uq_escalation_unresolved_case",
            "escalations",
            ["case_reference"],
            unique=True,
            sqlite_where=sa.text(f"status IN {ACTIVE_STATUSES}"),
            postgresql_where=sa.text(f"status IN {ACTIVE_STATUSES}"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "uq_escalation_unresolved_case" in {item.get("name") for item in inspector.get_indexes("escalations")}:
        op.drop_index("uq_escalation_unresolved_case", table_name="escalations")
    inspector = sa.inspect(bind)
    if "ck_escalation_status" in {item.get("name") for item in inspector.get_check_constraints("escalations")}:
        with op.batch_alter_table("escalations") as batch:
            batch.drop_constraint("ck_escalation_status", type_="check")
