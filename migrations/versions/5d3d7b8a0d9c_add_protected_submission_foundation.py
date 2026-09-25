"""Add protected citizen submission records and append-only event history.

Revision ID: 5d3d7b8a0d9c
Revises: c4d8e1f0a7b2
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5d3d7b8a0d9c'
down_revision = 'c4d8e1f0a7b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.String(length=50), nullable=False),
        sa.Column('citizen_id', sa.String(length=13), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('incident_date', sa.String(length=50), nullable=True),
        sa.Column('location', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='RECEIVED'),
        sa.Column('original_content', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('provenance', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('receipt_timestamp', sa.String(length=50), nullable=False),
        sa.Column('event_history', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_submissions_citizen_id'), 'submissions', ['citizen_id'], unique=False)
    op.create_index(op.f('ix_submissions_submission_id'), 'submissions', ['submission_id'], unique=True)
    op.create_index(op.f('ix_submissions_status'), 'submissions', ['status'], unique=False)

    op.create_table(
        'submission_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(length=50), nullable=False),
        sa.Column('submission_id', sa.String(length=50), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('actor_id', sa.String(length=13), nullable=False),
        sa.Column('actor_role', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.String(length=50), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_submission_events_event_id'), 'submission_events', ['event_id'], unique=True)
    op.create_index(op.f('ix_submission_events_submission_id'), 'submission_events', ['submission_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_submission_events_submission_id'), table_name='submission_events')
    op.drop_index(op.f('ix_submission_events_event_id'), table_name='submission_events')
    op.drop_table('submission_events')
    op.drop_index(op.f('ix_submissions_status'), table_name='submissions')
    op.drop_index(op.f('ix_submissions_submission_id'), table_name='submissions')
    op.drop_index(op.f('ix_submissions_citizen_id'), table_name='submissions')
    op.drop_table('submissions')
