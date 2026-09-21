"""Milestone 4: Objective Deterministic Decision Engine schema

Adds statutory-referral metadata to escalations, suspension state to
assignments, the objective tier/sanction determination and closure fields to
disciplinary cases, and the conflict_declarations table.

Revision ID: c4d8e1f0a7b2
Revises: 84d740a5539c
Create Date: 2026-09-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d8e1f0a7b2'
down_revision = '84d740a5539c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # escalations: statutory (IPID Act s28) referral metadata
    op.add_column('escalations', sa.Column('source', sa.String(length=50), nullable=False, server_default='MANUAL'))
    op.add_column('escalations', sa.Column('statutory_basis', sa.Text(), nullable=True))
    op.add_column('escalations', sa.Column('rule_code', sa.String(length=300), nullable=True))
    op.add_column('escalations', sa.Column('referral_trigger', sa.String(length=50), nullable=True))
    op.add_column('escalations', sa.Column('implicated_officer_id', sa.String(length=100), nullable=True))

    # assignments: SUSPENDED state applied when a statutory freeze strips write permissions
    op.add_column('assignments', sa.Column('suspended_at', sa.String(length=50), nullable=True))
    op.add_column('assignments', sa.Column('suspended_by', sa.String(length=100), nullable=True))
    op.add_column('assignments', sa.Column('suspension_reason', sa.Text(), nullable=True))

    # disciplinary_cases: objective determination + closure
    op.add_column('disciplinary_cases', sa.Column('misconduct_tier', sa.Integer(), nullable=True))
    op.add_column('disciplinary_cases', sa.Column('infraction_type', sa.String(length=60), nullable=True))
    op.add_column('disciplinary_cases', sa.Column('mandatory_sanction', sa.String(length=30), nullable=True))
    op.add_column('disciplinary_cases', sa.Column('determination', sa.JSON(), nullable=True))
    op.add_column('disciplinary_cases', sa.Column('determined_at', sa.String(length=50), nullable=True))
    op.add_column('disciplinary_cases', sa.Column('final_sanction', sa.String(length=30), nullable=True))
    op.add_column('disciplinary_cases', sa.Column('deviation_justification', sa.Text(), nullable=True))
    op.add_column('disciplinary_cases', sa.Column('closed_at', sa.String(length=50), nullable=True))
    op.add_column('disciplinary_cases', sa.Column('closed_by', sa.String(length=100), nullable=True))

    op.create_table('conflict_declarations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('declaration_id', sa.String(length=50), nullable=False),
    sa.Column('officer_id', sa.String(length=100), nullable=False),
    sa.Column('officer_role', sa.String(length=50), nullable=True),
    sa.Column('case_reference', sa.String(length=50), nullable=True),
    sa.Column('party_id', sa.String(length=100), nullable=True),
    sa.Column('relationship_type', sa.String(length=30), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('declared_by', sa.String(length=100), nullable=True),
    sa.Column('declared_by_role', sa.String(length=50), nullable=True),
    sa.Column('declared_at', sa.String(length=50), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conflict_declarations_declaration_id'), 'conflict_declarations', ['declaration_id'], unique=True)
    op.create_index(op.f('ix_conflict_declarations_officer_id'), 'conflict_declarations', ['officer_id'], unique=False)
    op.create_index(op.f('ix_conflict_declarations_case_reference'), 'conflict_declarations', ['case_reference'], unique=False)
    op.create_index(op.f('ix_conflict_declarations_party_id'), 'conflict_declarations', ['party_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_conflict_declarations_party_id'), table_name='conflict_declarations')
    op.drop_index(op.f('ix_conflict_declarations_case_reference'), table_name='conflict_declarations')
    op.drop_index(op.f('ix_conflict_declarations_officer_id'), table_name='conflict_declarations')
    op.drop_index(op.f('ix_conflict_declarations_declaration_id'), table_name='conflict_declarations')
    op.drop_table('conflict_declarations')

    with op.batch_alter_table('disciplinary_cases') as batch_op:
        for column in ('closed_by', 'closed_at', 'deviation_justification', 'final_sanction', 'determined_at',
                       'determination', 'mandatory_sanction', 'infraction_type', 'misconduct_tier'):
            batch_op.drop_column(column)
    with op.batch_alter_table('assignments') as batch_op:
        for column in ('suspension_reason', 'suspended_by', 'suspended_at'):
            batch_op.drop_column(column)
    with op.batch_alter_table('escalations') as batch_op:
        for column in ('implicated_officer_id', 'referral_trigger', 'rule_code', 'statutory_basis', 'source'):
            batch_op.drop_column(column)
