"""manager approval grants

Revision ID: 0008_manager_approval_grants
Revises: 0007_staff_identity
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0008_manager_approval_grants'
down_revision = '0007_staff_identity'
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column['name'] for column in inspect(op.get_bind()).get_columns('manager_approvals')}


def _indexes() -> set[str]:
    return {index['name'] for index in inspect(op.get_bind()).get_indexes('manager_approvals')}


def upgrade():
    columns = _columns()
    if 'payload_digest' not in columns:
        op.add_column('manager_approvals', sa.Column('payload_digest', sa.String(length=64), nullable=True))
    if 'expires_at_text' not in columns:
        op.add_column('manager_approvals', sa.Column('expires_at_text', sa.String(length=80), nullable=True))
    if 'consumed_at_text' not in columns:
        op.add_column('manager_approvals', sa.Column('consumed_at_text', sa.String(length=80), nullable=True))

    indexes = _indexes()
    if 'ix_manager_approvals_payload_digest' not in indexes:
        op.create_index('ix_manager_approvals_payload_digest', 'manager_approvals', ['payload_digest'], unique=False)
    if 'ix_manager_approvals_expires_at_text' not in indexes:
        op.create_index('ix_manager_approvals_expires_at_text', 'manager_approvals', ['expires_at_text'], unique=False)
    if 'ix_manager_approvals_consumed_at_text' not in indexes:
        op.create_index('ix_manager_approvals_consumed_at_text', 'manager_approvals', ['consumed_at_text'], unique=False)


def downgrade():
    indexes = _indexes()
    if 'ix_manager_approvals_consumed_at_text' in indexes:
        op.drop_index('ix_manager_approvals_consumed_at_text', table_name='manager_approvals')
    if 'ix_manager_approvals_expires_at_text' in indexes:
        op.drop_index('ix_manager_approvals_expires_at_text', table_name='manager_approvals')
    if 'ix_manager_approvals_payload_digest' in indexes:
        op.drop_index('ix_manager_approvals_payload_digest', table_name='manager_approvals')

    columns = _columns()
    if 'consumed_at_text' in columns:
        op.drop_column('manager_approvals', 'consumed_at_text')
    if 'expires_at_text' in columns:
        op.drop_column('manager_approvals', 'expires_at_text')
    if 'payload_digest' in columns:
        op.drop_column('manager_approvals', 'payload_digest')
