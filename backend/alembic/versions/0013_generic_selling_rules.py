"""Persist generic Inventory selling rules.

Revision ID: 0013_generic_selling_rules
Revises: 0012_catalog_pricing_rules
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_generic_selling_rules"
down_revision = "0012_catalog_pricing_rules"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("catalog_items")}
    if "pricing_tags_json" not in columns:
        op.add_column("catalog_items", sa.Column("pricing_tags_json", sa.Text(), nullable=True))
    if "conditional_prices_json" not in columns:
        op.add_column("catalog_items", sa.Column("conditional_prices_json", sa.Text(), nullable=True))


def downgrade():
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("catalog_items")}
    if "conditional_prices_json" in columns:
        op.drop_column("catalog_items", "conditional_prices_json")
    if "pricing_tags_json" in columns:
        op.drop_column("catalog_items", "pricing_tags_json")
