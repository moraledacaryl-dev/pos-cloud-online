from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.services.recipe_service import (
    MAX_RECIPE_PDF_BYTES,
    delete_recipe_document,
    get_recipe_document,
    list_recipe_dishes,
    list_recipe_documents,
    upsert_recipe_document,
)

router = APIRouter()


@router.get('/dishes')
def dishes(q: str | None = None, db: Session = Depends(get_db), user=Depends(require_permissions('recipes.view'))):
    return list_recipe_dishes(db, q=q)


@router.get('/')
def documents(q: str | None = None, db: Session = Depends(get_db), user=Depends(require_permissions('recipes.view'))):
    return list_recipe_documents(db, q=q)


@router.get('/{external_menu_item_id}/pdf')
def open_pdf(external_menu_item_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('recipes.view'))):
    try:
        row = get_recipe_document(db, external_menu_item_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    filename = row.original_filename.replace('"', '')
    return Response(
        content=row.pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'inline; filename="{filename}"',
            'Content-Length': str(row.file_size),
        },
    )


@router.put('/{external_menu_item_id}/pdf')
async def upload_pdf(
    external_menu_item_id: int,
    request: Request,
    filename: str = Query(default='recipe.pdf', max_length=255),
    title: str | None = Query(default=None, max_length=255),
    notes: str | None = Query(default=None, max_length=2000),
    db: Session = Depends(get_db),
    user=Depends(require_permissions('recipes.manage')),
):
    try:
        content_length = int(request.headers.get('content-length') or 0)
    except ValueError:
        raise HTTPException(status_code=400, detail='Invalid upload size.')
    if content_length > MAX_RECIPE_PDF_BYTES:
        raise HTTPException(status_code=413, detail='Recipe PDF must be 15 MB or smaller.')
    content_type = (request.headers.get('content-type') or '').split(';', 1)[0].strip().lower()
    if content_type != 'application/pdf':
        raise HTTPException(status_code=400, detail='Upload a PDF file.')
    try:
        return upsert_recipe_document(
            db,
            external_menu_item_id=external_menu_item_id,
            pdf_bytes=await request.body(),
            filename=filename,
            title=title,
            notes=notes,
            uploaded_by_user_id=user.id,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete('/{external_menu_item_id}')
def remove_pdf(external_menu_item_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('recipes.manage'))):
    try:
        return delete_recipe_document(db, external_menu_item_id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
