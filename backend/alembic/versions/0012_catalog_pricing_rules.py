"""add catalog pricing roles and modifiers

Revision ID: 0012_catalog_pricing_rules
Revises: 0011_inventory_catalog_ids
"""
from alembic import op
import sqlalchemy as sa
revision="0012_catalog_pricing_rules"
down_revision="0011_inventory_catalog_ids"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("catalog_items",sa.Column("with_drink_price",sa.Numeric(14,2),nullable=True))
    op.add_column("catalog_items",sa.Column("pricing_role",sa.String(24),nullable=False,server_default="standard"))
    op.add_column("catalog_items",sa.Column("modifier_groups_json",sa.Text(),nullable=True))

def downgrade():
    op.drop_column("catalog_items","modifier_groups_json")
    op.drop_column("catalog_items","pricing_role")
    op.drop_column("catalog_items","with_drink_price")
