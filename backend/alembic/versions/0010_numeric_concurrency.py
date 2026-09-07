"""use exact financial types and prevent duplicate open sessions

Revision ID: 0010_numeric_concurrency
Revises: 0009_customer_display_devices
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa


revision = '0010_numeric_concurrency'
down_revision = '0009_customer_display_devices'
branch_labels = None
depends_on = None


MONEY_COLUMNS = {
    'catalog_items': ('price',),
    'register_sessions': ('opening_float', 'closing_actual_cash', 'closing_expected_cash', 'variance_amount'),
    'pos_orders': ('subtotal_amount', 'discount_amount', 'tax_amount', 'service_charge_amount', 'total_amount', 'paid_amount', 'balance_due'),
    'pos_order_lines': ('unit_price', 'discount_amount', 'line_total'),
    'pos_order_payments': ('amount_applied', 'amount_received', 'change_given'),
    'room_charge_postings': ('charge_amount',),
    'cash_movements': ('amount',),
    'refunds': ('subtotal_amount', 'refunded_amount'),
    'refund_lines': ('unit_price', 'discount_amount', 'refunded_line_total'),
    'refund_payments': ('amount',),
}

QUANTITY_COLUMNS = {
    'pos_order_lines': ('quantity', 'ready_quantity'),
    'refund_lines': ('quantity',),
}

RATE_COLUMNS = {
    'catalog_items': ('tax_rate', 'service_charge_rate'),
}


def _columns(bind, table_name):
    return {column['name']: column for column in sa.inspect(bind).get_columns(table_name)}


def _convert_columns(table_name, column_names, target_type, *, only_float=True):
    bind = op.get_bind()
    columns = _columns(bind, table_name)
    pending = []
    for column_name in column_names:
        column = columns.get(column_name)
        if not column:
            continue
        if only_float and not isinstance(column['type'], (sa.Float, sa.REAL)):
            continue
        pending.append(column)
    if not pending:
        return
    with op.batch_alter_table(table_name) as batch:
        for column in pending:
            name = column['name']
            batch.alter_column(
                name,
                existing_type=column['type'],
                type_=target_type,
                existing_nullable=bool(column.get('nullable', True)),
                postgresql_using=f'ROUND({name}::numeric, {target_type.scale})',
            )


def upgrade():
    for table_name, columns in MONEY_COLUMNS.items():
        _convert_columns(table_name, columns, sa.Numeric(14, 2))
    for table_name, columns in QUANTITY_COLUMNS.items():
        _convert_columns(table_name, columns, sa.Numeric(12, 4))
    for table_name, columns in RATE_COLUMNS.items():
        _convert_columns(table_name, columns, sa.Numeric(9, 6))

    bind = op.get_bind()
    existing_indexes = {index['name'] for index in sa.inspect(bind).get_indexes('register_sessions')}
    if 'uq_register_sessions_one_open' not in existing_indexes:
        op.create_index(
            'uq_register_sessions_one_open',
            'register_sessions',
            ['register_id'],
            unique=True,
            postgresql_where=sa.text("status = 'open'"),
            sqlite_where=sa.text("status = 'open'"),
        )


def downgrade():
    bind = op.get_bind()
    existing_indexes = {index['name'] for index in sa.inspect(bind).get_indexes('register_sessions')}
    if 'uq_register_sessions_one_open' in existing_indexes:
        op.drop_index('uq_register_sessions_one_open', table_name='register_sessions')

    for column_group in (MONEY_COLUMNS, QUANTITY_COLUMNS, RATE_COLUMNS):
        for table_name, column_names in column_group.items():
            columns = _columns(bind, table_name)
            pending = [columns[name] for name in column_names if name in columns and isinstance(columns[name]['type'], sa.Numeric)]
            if not pending:
                continue
            with op.batch_alter_table(table_name) as batch:
                for column in pending:
                    name = column['name']
                    batch.alter_column(
                        name,
                        existing_type=column['type'],
                        type_=sa.Float(),
                        existing_nullable=bool(column.get('nullable', True)),
                        postgresql_using=f'{name}::double precision',
                    )
