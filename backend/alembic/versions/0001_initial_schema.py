"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-20
"""
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))

from alembic import op
from app.models.entities import Base

revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None

# 0001 historically used the live ORM metadata.  New tables added after 0001 must
# never leak into a fresh 0001 bootstrap, otherwise their later Alembic revision
# attempts to create them a second time.  Keep post-0001 tables excluded here;
# their owning migration remains the source of truth for creation.
POST_INITIAL_TABLES = {
    'customer_display_devices',  # owned by 0009_customer_display_devices
}

# 0001 still builds legacy tables from live ORM metadata. Columns introduced by
# later revisions must therefore be temporarily removed from that metadata during
# a fresh bootstrap, otherwise their owning migration sees duplicate columns.
POST_INITIAL_COLUMNS = {
    'catalog_items': {'inventory_menu_item_id', 'inventory_variant_id'},  # owned by 0011
}


def _initial_tables():
    return [table for table in Base.metadata.sorted_tables if table.name not in POST_INITIAL_TABLES]


def upgrade():
    bind = op.get_bind()
    removed = []
    for table_name, column_names in POST_INITIAL_COLUMNS.items():
        table = Base.metadata.tables.get(table_name)
        if table is None:
            continue
        for column_name in column_names:
            column = table.columns.get(column_name)
            if column is not None:
                table._columns.remove(column)
                removed.append((table, column))
    try:
        Base.metadata.create_all(bind=bind, tables=_initial_tables())
    finally:
        for table, column in removed:
            table.append_column(column)


def downgrade():
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=_initial_tables())
