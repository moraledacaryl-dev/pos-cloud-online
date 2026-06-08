"""catalog availability override

Revision ID: 0004_catalog_availability
Revises: 0003_room_charge_sync_tracking
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0004_catalog_availability'
down_revision = '0003_room_charge_sync_tracking'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    return any(col.get('name') == column_name for col in inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    if not _has_column('catalog_items', 'availability_override'):
        op.add_column('catalog_items', sa.Column('availability_override', sa.Boolean(), nullable=True))
        catalog_items = sa.table(
            'catalog_items',
            sa.column('availability_override', sa.Boolean()),
            sa.column('is_available', sa.Boolean()),
        )
        op.execute(
            catalog_items.update()
            .where(catalog_items.c.is_available == sa.false())
            .values(availability_override=False)
        )


def downgrade():
    if _has_column('catalog_items', 'availability_override'):
        op.drop_column('catalog_items', 'availability_override')
