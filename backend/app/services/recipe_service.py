from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models.entities import CatalogItem, RecipeDocument

MAX_RECIPE_PDF_BYTES = 15 * 1024 * 1024


def _clean_text(value: str | None, *, max_length: int | None = None) -> str | None:
    text = (value or '').strip()
    if not text:
        return None
    return text[:max_length] if max_length else text


def _safe_filename(value: str | None) -> str:
    filename = Path((value or 'recipe.pdf').replace('\\', '/')).name.strip()
    if not filename.lower().endswith('.pdf'):
        filename = f'{filename or "recipe"}.pdf'
    return filename[:255]


def _iso(value) -> str | None:
    if not value:
        return None
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def serialize_recipe_document(row: RecipeDocument | None) -> dict | None:
    if not row:
        return None
    return {
        'id': row.id,
        'external_menu_item_id': row.external_menu_item_id,
        'dish_name': row.dish_name_snapshot,
        'category_name': row.category_name,
        'title': row.title,
        'original_filename': row.original_filename,
        'content_type': row.content_type,
        'file_size': row.file_size,
        'notes': row.notes,
        'uploaded_by_user_id': row.uploaded_by_user_id,
        'uploaded_by_name': row.uploaded_by.full_name or row.uploaded_by.username if row.uploaded_by else None,
        'created_at': _iso(row.created_at),
        'updated_at': _iso(row.updated_at),
    }


def _linked_catalog_items(db: Session, external_menu_item_id: int) -> list[CatalogItem]:
    return (
        db.query(CatalogItem)
        .filter(CatalogItem.external_menu_item_id == int(external_menu_item_id))
        .order_by(CatalogItem.sort_order.asc(), CatalogItem.id.asc())
        .all()
    )


def list_recipe_dishes(db: Session, *, q: str | None = None) -> list[dict]:
    catalog_rows = (
        db.query(CatalogItem)
        .filter(CatalogItem.external_menu_item_id.isnot(None))
        .order_by(CatalogItem.category_name.asc(), CatalogItem.menu_item_name.asc(), CatalogItem.sort_order.asc(), CatalogItem.id.asc())
        .all()
    )
    documents = {
        row.external_menu_item_id: row
        for row in db.query(RecipeDocument).all()
    }
    grouped: dict[int, dict] = {}
    for item in catalog_rows:
        menu_item_id = int(item.external_menu_item_id)
        group = grouped.setdefault(menu_item_id, {
            'external_menu_item_id': menu_item_id,
            'dish_name': item.menu_item_name,
            'category_name': item.category_name,
            'module_slug': item.module_slug,
            'variant_count': 0,
            'variants': [],
            'recipe': serialize_recipe_document(documents.get(menu_item_id)),
        })
        group['variant_count'] += 1
        variant_label = item.variant_name or item.display_name
        if variant_label and variant_label not in group['variants']:
            group['variants'].append(variant_label)

    rows = list(grouped.values())
    search = _clean_text(q)
    if search:
        needle = search.casefold()
        rows = [
            row for row in rows
            if needle in ' '.join([
                row.get('dish_name') or '',
                row.get('category_name') or '',
                row.get('module_slug') or '',
                ' '.join(row.get('variants') or []),
            ]).casefold()
        ]
    return rows


def list_recipe_documents(db: Session, *, q: str | None = None) -> list[dict]:
    rows = db.query(RecipeDocument).order_by(RecipeDocument.category_name.asc(), RecipeDocument.dish_name_snapshot.asc()).all()
    search = _clean_text(q)
    if search:
        needle = search.casefold()
        rows = [
            row for row in rows
            if needle in ' '.join([row.dish_name_snapshot or '', row.category_name or '', row.title or '', row.notes or '']).casefold()
        ]
    return [serialize_recipe_document(row) for row in rows]


def get_recipe_document(db: Session, external_menu_item_id: int) -> RecipeDocument:
    row = db.query(RecipeDocument).filter(RecipeDocument.external_menu_item_id == int(external_menu_item_id)).first()
    if not row:
        raise ValueError('Recipe PDF not found for this dish.')
    return row


def upsert_recipe_document(
    db: Session,
    *,
    external_menu_item_id: int,
    pdf_bytes: bytes,
    filename: str | None,
    title: str | None = None,
    notes: str | None = None,
    uploaded_by_user_id: int | None = None,
) -> dict:
    linked_items = _linked_catalog_items(db, external_menu_item_id)
    if not linked_items:
        raise ValueError('Recipe PDFs can only be attached to dishes synced from Accounting.')
    if not pdf_bytes:
        raise ValueError('Choose a PDF file to upload.')
    if len(pdf_bytes) > MAX_RECIPE_PDF_BYTES:
        raise ValueError('Recipe PDF must be 15 MB or smaller.')
    if not pdf_bytes.startswith(b'%PDF'):
        raise ValueError('The uploaded file is not a valid PDF.')

    first = linked_items[0]
    row = db.query(RecipeDocument).filter(RecipeDocument.external_menu_item_id == int(external_menu_item_id)).first()
    if not row:
        row = RecipeDocument(external_menu_item_id=int(external_menu_item_id))
    row.dish_name_snapshot = first.menu_item_name
    row.category_name = first.category_name
    row.title = _clean_text(title, max_length=255) or first.menu_item_name
    row.original_filename = _safe_filename(filename)
    row.content_type = 'application/pdf'
    row.file_size = len(pdf_bytes)
    row.pdf_bytes = pdf_bytes
    row.notes = _clean_text(notes, max_length=2000)
    row.uploaded_by_user_id = uploaded_by_user_id
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_recipe_document(row)


def delete_recipe_document(db: Session, external_menu_item_id: int) -> dict:
    row = get_recipe_document(db, external_menu_item_id)
    db.delete(row)
    db.commit()
    return {'ok': True}
