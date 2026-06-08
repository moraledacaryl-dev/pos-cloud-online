"""recipe PDF documents

Revision ID: 0005_recipe_documents
Revises: 0004_catalog_availability
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0005_recipe_documents'
down_revision = '0004_catalog_availability'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def upgrade():
    if _has_table('recipe_documents'):
        return
    op.create_table(
        'recipe_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_menu_item_id', sa.Integer(), nullable=False),
        sa.Column('dish_name_snapshot', sa.String(length=180), nullable=False),
        sa.Column('category_name', sa.String(length=120), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=120), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('pdf_bytes', sa.LargeBinary(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_menu_item_id', name='uq_recipe_document_menu_item'),
    )
    op.create_index(op.f('ix_recipe_documents_category_name'), 'recipe_documents', ['category_name'], unique=False)
    op.create_index(op.f('ix_recipe_documents_dish_name_snapshot'), 'recipe_documents', ['dish_name_snapshot'], unique=False)
    op.create_index(op.f('ix_recipe_documents_external_menu_item_id'), 'recipe_documents', ['external_menu_item_id'], unique=True)
    op.create_index(op.f('ix_recipe_documents_uploaded_by_user_id'), 'recipe_documents', ['uploaded_by_user_id'], unique=False)


def downgrade():
    if _has_table('recipe_documents'):
        op.drop_table('recipe_documents')
