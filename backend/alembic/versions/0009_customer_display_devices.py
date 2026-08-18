"""customer display devices

Revision ID: 0009_customer_display_devices
Revises: 0008_manager_approval_grants
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa

revision = '0009_customer_display_devices'
down_revision = '0008_manager_approval_grants'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'customer_display_devices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('device_uuid', sa.String(length=80), nullable=False),
        sa.Column('credential_hash', sa.String(length=64), nullable=False),
        sa.Column('channel', sa.String(length=40), nullable=False),
        sa.Column('register_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('expires_at', sa.String(length=80), nullable=True),
        sa.Column('last_seen_at', sa.String(length=80), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('revoked_at', sa.String(length=80), nullable=True),
        sa.UniqueConstraint('device_uuid', name='uq_customer_display_device_uuid'),
        sa.UniqueConstraint('credential_hash', name='uq_customer_display_credential_hash'),
    )
    op.create_index('ix_customer_display_devices_device_uuid', 'customer_display_devices', ['device_uuid'])
    op.create_index('ix_customer_display_devices_credential_hash', 'customer_display_devices', ['credential_hash'])
    op.create_index('ix_customer_display_devices_channel', 'customer_display_devices', ['channel'])
    op.create_index('ix_customer_display_devices_register_id', 'customer_display_devices', ['register_id'])
    op.create_index('ix_customer_display_devices_is_active', 'customer_display_devices', ['is_active'])
    op.create_index('ix_customer_display_devices_expires_at', 'customer_display_devices', ['expires_at'])
    op.create_index('ix_customer_display_devices_last_seen_at', 'customer_display_devices', ['last_seen_at'])
    op.create_index('ix_customer_display_devices_revoked_at', 'customer_display_devices', ['revoked_at'])


def downgrade():
    op.drop_table('customer_display_devices')
