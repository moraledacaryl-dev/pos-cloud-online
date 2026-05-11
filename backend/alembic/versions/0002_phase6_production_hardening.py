"""phase 6 production hardening

Revision ID: 0002_phase6_production_hardening
Revises: 0001_initial_schema
Create Date: 2026-04-20
"""

from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0002_phase6_production_hardening'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return any(col.get('name') == column_name for col in inspector.get_columns(table_name))


def upgrade():
    if not _has_column('users', 'session_version'):
        op.add_column('users', sa.Column('session_version', sa.Integer(), nullable=False, server_default='1'))
    if not _has_column('users', 'force_logout_after_text'):
        op.add_column('users', sa.Column('force_logout_after_text', sa.String(length=50), nullable=True))
        op.create_index('ix_users_force_logout_after_text', 'users', ['force_logout_after_text'], unique=False)
    if not _has_column('refresh_tokens', 'session_version'):
        op.add_column('refresh_tokens', sa.Column('session_version', sa.Integer(), nullable=False, server_default='1'))
        op.create_index('ix_refresh_tokens_session_version', 'refresh_tokens', ['session_version'], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    token_cols = {c.get('name') for c in inspector.get_columns('refresh_tokens')}
    user_cols = {c.get('name') for c in inspector.get_columns('users')}
    token_indexes = {i.get('name') for i in inspector.get_indexes('refresh_tokens')}
    user_indexes = {i.get('name') for i in inspector.get_indexes('users')}
    if 'ix_refresh_tokens_session_version' in token_indexes:
        op.drop_index('ix_refresh_tokens_session_version', table_name='refresh_tokens')
    if 'session_version' in token_cols:
        op.drop_column('refresh_tokens', 'session_version')
    if 'ix_users_force_logout_after_text' in user_indexes:
        op.drop_index('ix_users_force_logout_after_text', table_name='users')
    if 'force_logout_after_text' in user_cols:
        op.drop_column('users', 'force_logout_after_text')
    if 'session_version' in user_cols:
        op.drop_column('users', 'session_version')
