"""canonical Staff identity and POS user links

Revision ID: 0007_staff_identity
Revises: 0006_pos_order_service_area
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0007_staff_identity'
down_revision = '0006_pos_order_service_area'
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade():
    tables = _tables()
    if 'staff_identities' not in tables:
        op.create_table(
            'staff_identities',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('source_staff_id', sa.Integer(), nullable=False),
            sa.Column('employee_code', sa.String(length=120), nullable=False),
            sa.Column('display_name', sa.String(length=255), nullable=False),
            sa.Column('department', sa.String(length=160), nullable=True),
            sa.Column('position', sa.String(length=160), nullable=True),
            sa.Column('staff_role', sa.String(length=120), nullable=True),
            sa.Column('primary_department', sa.String(length=160), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('last_external_id', sa.String(length=255), nullable=True),
            sa.Column('last_synced_at_text', sa.String(length=80), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('source_staff_id', name='uq_staff_identities_source_staff_id'),
            sa.UniqueConstraint('employee_code', name='uq_staff_identities_employee_code'),
        )
        op.create_index('ix_staff_identities_source_staff_id', 'staff_identities', ['source_staff_id'], unique=True)
        op.create_index('ix_staff_identities_employee_code', 'staff_identities', ['employee_code'], unique=True)
        op.create_index('ix_staff_identities_display_name', 'staff_identities', ['display_name'], unique=False)
        op.create_index('ix_staff_identities_department', 'staff_identities', ['department'], unique=False)
        op.create_index('ix_staff_identities_is_active', 'staff_identities', ['is_active'], unique=False)
        op.create_index('ix_staff_identities_last_external_id', 'staff_identities', ['last_external_id'], unique=False)
        op.create_index('ix_staff_identities_last_synced_at_text', 'staff_identities', ['last_synced_at_text'], unique=False)

    if 'pos_user_staff_links' not in tables:
        op.create_table(
            'pos_user_staff_links',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('staff_identity_id', sa.Integer(), sa.ForeignKey('staff_identities.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('user_id', name='uq_pos_user_staff_link_user'),
            sa.UniqueConstraint('staff_identity_id', name='uq_pos_user_staff_link_identity'),
        )
        op.create_index('ix_pos_user_staff_links_user_id', 'pos_user_staff_links', ['user_id'], unique=True)
        op.create_index('ix_pos_user_staff_links_staff_identity_id', 'pos_user_staff_links', ['staff_identity_id'], unique=True)


def downgrade():
    tables = _tables()
    if 'pos_user_staff_links' in tables:
        op.drop_table('pos_user_staff_links')
    if 'staff_identities' in tables:
        op.drop_table('staff_identities')
