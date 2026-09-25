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

    op.create_index(
        "uq_escalation_unresolved_case",
        "escalations",
        ["case_reference"],
        unique=True,
        sqlite_where=sa.text(f"status IN {ACTIVE_STATUSES}"),
        postgresql_where=sa.text(f"status IN {ACTIVE_STATUSES}"),
    )


def downgrade() -> None:
    op.drop_index("uq_escalation_unresolved_case", table_name="escalations")
