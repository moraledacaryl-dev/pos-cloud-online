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

    # This migration introduced two user-editable selling-rule columns. A
    # blind downgrade would permanently discard populated rule data. Refuse
    # to downgrade when either field has values so an operator can arrange an
    # approved export/recovery path instead of silent pricing data loss.
    existing = [
        field for field in ("conditional_prices_json", "pricing_tags_json")
        if field in columns
    ]
    if existing:
        nonnull = " OR ".join(f"{field} IS NOT NULL" for field in existing)
        populated = connection.execute(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM catalog_items WHERE {nonnull})")
        ).scalar_one()
        if populated:
            raise RuntimeError(
                "0013 downgrade blocked: populated conditional pricing/tags "
                "would be lost; preserve selling rules before an approved rollback."
            )

    if "conditional_prices_json" in columns:
        op.drop_column("catalog_items", "conditional_prices_json")
    if "pricing_tags_json" in columns:
        op.drop_column("catalog_items", "pricing_tags_json")
