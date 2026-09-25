"""Compliance rule engine foundation.

Revision ID: d7b3a4c5e6f7
Revises: c4d8e1f0a7b2
"""

from alembic import op
import sqlalchemy as sa


revision = "d7b3a4c5e6f7"
down_revision = "c4d8e1f0a7b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "compliance_flags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("flag_id", sa.String(length=100), nullable=False),
        sa.Column("rule_code", sa.String(length=10), nullable=False),
        sa.Column("case_reference", sa.String(length=50), nullable=True),
        sa.Column("subject_officer_id", sa.String(length=100), nullable=True),
        sa.Column("actor_role", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("raised_at", sa.String(length=50), nullable=False),
        sa.Column("due_at", sa.String(length=50), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("legal_reference_id", sa.String(length=100), nullable=False),
        sa.Column("provision", sa.String(length=200), nullable=False),
        sa.Column("corpus_version", sa.Integer(), nullable=False),
        sa.Column("verification", sa.String(length=20), nullable=False),
        sa.Column("routes_to", sa.String(length=50), nullable=False),
        sa.Column("officer_response", sa.Text(), nullable=True),
        sa.Column("responded_at", sa.String(length=50), nullable=True),
        sa.Column("resolved_by", sa.String(length=100), nullable=True),
        sa.Column("resolved_at", sa.String(length=50), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("flag_id"),
    )
    op.create_index("ix_compliance_flags_flag_id", "compliance_flags", ["flag_id"], unique=True)
    op.create_index("ix_compliance_flags_rule_code", "compliance_flags", ["rule_code"], unique=False)
    op.create_index("ix_compliance_flags_case_reference", "compliance_flags", ["case_reference"], unique=False)
    op.create_index("ix_compliance_flags_subject_officer_id", "compliance_flags", ["subject_officer_id"], unique=False)
    op.create_index("ix_compliance_flags_status", "compliance_flags", ["status"], unique=False)


def downgrade():
    op.drop_index("ix_compliance_flags_status", table_name="compliance_flags")
    op.drop_index("ix_compliance_flags_subject_officer_id", table_name="compliance_flags")
    op.drop_index("ix_compliance_flags_case_reference", table_name="compliance_flags")
    op.drop_index("ix_compliance_flags_rule_code", table_name="compliance_flags")
    op.drop_index("ix_compliance_flags_flag_id", table_name="compliance_flags")
    op.drop_table("compliance_flags")