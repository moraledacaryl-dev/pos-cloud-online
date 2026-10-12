"""add Inventory catalog source identifiers

Revision ID: 0011_inventory_catalog_ids
Revises: 0010_numeric_concurrency
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_inventory_catalog_ids"
down_revision = "0010_numeric_concurrency"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("catalog_items", sa.Column("inventory_menu_item_id", sa.String(length=80), nullable=True))
    op.add_column("catalog_items", sa.Column("inventory_variant_id", sa.String(length=80), nullable=True))
    op.create_index("ix_catalog_items_inventory_menu_item_id", "catalog_items", ["inventory_menu_item_id"], unique=False)
    op.create_index("ix_catalog_items_inventory_variant_id", "catalog_items", ["inventory_variant_id"], unique=True)

def downgrade():
    op.drop_index("ix_catalog_items_inventory_variant_id", table_name="catalog_items")
    op.drop_index("ix_catalog_items_inventory_menu_item_id", table_name="catalog_items")
    op.drop_column("catalog_items", "inventory_variant_id")
    op.drop_column("catalog_items", "inventory_menu_item_id")
