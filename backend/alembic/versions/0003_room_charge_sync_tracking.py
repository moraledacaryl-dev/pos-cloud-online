"""room charge sync tracking

Revision ID: 0003_room_charge_sync_tracking
Revises: 0002_phase6_production_hardening
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0003_room_charge_sync_tracking'
down_revision = '0002_phase6_production_hardening'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(col.get('name') == column_name for col in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    if not _has_column('room_charge_postings', 'synced_to_accounting'):
        op.add_column('room_charge_postings', sa.Column('synced_to_accounting', sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _has_index('room_charge_postings', 'ix_room_charge_postings_synced_to_accounting'):
        op.create_index('ix_room_charge_postings_synced_to_accounting', 'room_charge_postings', ['synced_to_accounting'], unique=False)
    if not _has_column('room_charge_postings', 'last_sync_at'):
        op.add_column('room_charge_postings', sa.Column('last_sync_at', sa.String(length=50), nullable=True))
    if not _has_index('room_charge_postings', 'ix_room_charge_postings_last_sync_at'):
        op.create_index('ix_room_charge_postings_last_sync_at', 'room_charge_postings', ['last_sync_at'], unique=False)


def downgrade():
    if _has_index('room_charge_postings', 'ix_room_charge_postings_last_sync_at'):
        op.drop_index('ix_room_charge_postings_last_sync_at', table_name='room_charge_postings')
    if _has_column('room_charge_postings', 'last_sync_at'):
        op.drop_column('room_charge_postings', 'last_sync_at')
    if _has_index('room_charge_postings', 'ix_room_charge_postings_synced_to_accounting'):
        op.drop_index('ix_room_charge_postings_synced_to_accounting', table_name='room_charge_postings')
    if _has_column('room_charge_postings', 'synced_to_accounting'):
        op.drop_column('room_charge_postings', 'synced_to_accounting')
