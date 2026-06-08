import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import CatalogItem, RecipeDocument, User
from app.services.auth_service import hash_password
from app.services.permission_service import ROLE_PERMISSION_PRESETS
from app.services.recipe_service import delete_recipe_document, get_recipe_document, list_recipe_dishes, upsert_recipe_document


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed_catalog(db):
    manager = User(username='manager', full_name='Recipe Manager', hashed_password=hash_password('secret123'), role='manager', is_active=True)
    rows = [
        CatalogItem(external_menu_item_id=101, external_sku_id=201, menu_item_name='Iced Coffee', display_name='Iced Coffee - Regular', variant_name='Regular', category_name='Beverages', module_slug='restaurant', price=100),
        CatalogItem(external_menu_item_id=101, external_sku_id=202, menu_item_name='Iced Coffee', display_name='Iced Coffee - Large', variant_name='Large', category_name='Beverages', module_slug='restaurant', price=130),
        CatalogItem(external_menu_item_id=102, external_sku_id=None, menu_item_name='Club Sandwich', display_name='Club Sandwich', category_name='Meals', module_slug='restaurant', price=240),
        CatalogItem(external_menu_item_id=None, external_sku_id=None, menu_item_name='Emergency Item', display_name='Emergency Item', category_name='Fallback', module_slug='restaurant', price=1),
    ]
    db.add_all([manager, *rows])
    db.commit()
    db.refresh(manager)
    return manager


def test_recipe_dishes_group_synced_skus_and_exclude_local_fallbacks():
    db = make_session()
    seed_catalog(db)

    rows = list_recipe_dishes(db)

    assert len(rows) == 2
    coffee = next(row for row in rows if row['external_menu_item_id'] == 101)
    assert coffee['dish_name'] == 'Iced Coffee'
    assert coffee['variant_count'] == 2
    assert coffee['variants'] == ['Regular', 'Large']
    assert all(row['dish_name'] != 'Emergency Item' for row in rows)


def test_recipe_pdf_upload_replaces_one_document_and_can_be_removed():
    db = make_session()
    manager = seed_catalog(db)

    first = upsert_recipe_document(db, external_menu_item_id=101, pdf_bytes=b'%PDF-1.4 first', filename='coffee.pdf', title='Coffee Recipe', notes='Use cold brew.', uploaded_by_user_id=manager.id)
    second = upsert_recipe_document(db, external_menu_item_id=101, pdf_bytes=b'%PDF-1.7 replacement', filename='../coffee-v2.pdf', title='Coffee Recipe v2', uploaded_by_user_id=manager.id)

    assert first['external_menu_item_id'] == 101
    assert second['title'] == 'Coffee Recipe v2'
    assert second['original_filename'] == 'coffee-v2.pdf'
    assert db.query(RecipeDocument).count() == 1
    assert get_recipe_document(db, 101).pdf_bytes == b'%PDF-1.7 replacement'
    assert list_recipe_dishes(db, q='large')[0]['recipe']['title'] == 'Coffee Recipe v2'
    assert delete_recipe_document(db, 101) == {'ok': True}
    assert db.query(RecipeDocument).count() == 0


def test_recipe_pdf_upload_rejects_invalid_and_non_accounting_files():
    db = make_session()
    seed_catalog(db)

    with pytest.raises(ValueError, match='valid PDF'):
        upsert_recipe_document(db, external_menu_item_id=101, pdf_bytes=b'not a pdf', filename='bad.pdf')
    with pytest.raises(ValueError, match='synced from Accounting'):
        upsert_recipe_document(db, external_menu_item_id=999, pdf_bytes=b'%PDF-1.4', filename='missing.pdf')


def test_staff_role_presets_can_view_but_only_managers_manage_recipe_pdfs():
    assert {'recipes.view', 'recipes.manage'} <= ROLE_PERMISSION_PRESETS['manager']
    assert 'recipes.view' in ROLE_PERMISSION_PRESETS['cashier']
    assert 'recipes.view' in ROLE_PERMISSION_PRESETS['kitchen']
    assert 'recipes.manage' not in ROLE_PERMISSION_PRESETS['cashier']
    assert 'recipes.manage' not in ROLE_PERMISSION_PRESETS['kitchen']
