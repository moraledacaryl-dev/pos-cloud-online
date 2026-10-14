"""persist generic Inventory selling rules

Revision ID: 0013_generic_selling_rules
Revises: 0012_catalog_pricing_rules
"""
from alembic import op
import sqlalchemy as sa
revision="0013_generic_selling_rules"
down_revision="0012_catalog_pricing_rules"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("catalog_items",sa.Column("pricing_tags_json",sa.Text(),nullable=True))
    op.add_column("catalog_items",sa.Column("conditional_prices_json",sa.Text(),nullable=True))
def downgrade():
    op.drop_column("catalog_items","conditional_prices_json")
    op.drop_column("catalog_items","pricing_tags_json")
