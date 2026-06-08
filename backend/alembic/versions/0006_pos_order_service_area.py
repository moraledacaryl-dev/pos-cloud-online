"""pos order service area

Revision ID: 0006_pos_order_service_area
Revises: 0005_recipe_documents
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0006_pos_order_service_area'
down_revision = '0005_recipe_documents'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column['name'] for column in inspector.get_columns(table_name)}


def _has_index(index_name: str, table_name: str) -> bool:
    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return index_name in {index['name'] for index in inspector.get_indexes(table_name)}


def upgrade():
    if not _has_column('pos_orders', 'service_area'):
        op.add_column('pos_orders', sa.Column('service_area', sa.String(length=80), nullable=True))
    if not _has_index('ix_pos_orders_service_area', 'pos_orders'):
        op.create_index(op.f('ix_pos_orders_service_area'), 'pos_orders', ['service_area'], unique=False)


def downgrade():
    if _has_index('ix_pos_orders_service_area', 'pos_orders'):
        op.drop_index(op.f('ix_pos_orders_service_area'), table_name='pos_orders')
    if _has_column('pos_orders', 'service_area'):
        op.drop_column('pos_orders', 'service_area')
