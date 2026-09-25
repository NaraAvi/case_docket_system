"""Add case procedural assessment payload.

Revision ID: f5b2a08d9cc3
Revises: 5d3d7b8a0d9c
Create Date: 2026-09-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f5b2a08d9cc3'
down_revision = '5d3d7b8a0d9c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('case_dockets') as batch_op:
        batch_op.add_column(
            sa.Column('procedural_assessment', sa.JSON(), nullable=True, server_default=sa.text("'{}'"))
        )

    op.execute("UPDATE case_dockets SET procedural_assessment = '{}' WHERE procedural_assessment IS NULL")

    with op.batch_alter_table('case_dockets') as batch_op:
        batch_op.alter_column('procedural_assessment', nullable=False, server_default=sa.text("'{}'"))


def downgrade() -> None:
    with op.batch_alter_table('case_dockets') as batch_op:
        batch_op.drop_column('procedural_assessment')
