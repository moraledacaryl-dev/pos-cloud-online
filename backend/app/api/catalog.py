from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.schemas.common import CatalogItemCreate, CatalogItemUpdate
from app.services.catalog_policy import build_catalog_sync_status
from app.services.pos_service import create_catalog_item, delete_catalog_item, list_catalog_items, setting_json, update_catalog_item
from app.services.sync_service import sync_catalog_from_accounting

router = APIRouter()


@router.get('/items')
def items(active_only: bool = False, available_only: bool = False, q: str | None = None, db: Session = Depends(get_db), user=Depends(require_permissions('catalog.view'))):
    return list_catalog_items(db, active_only=active_only, available_only=available_only, q=q)


@router.get('/status')
def catalog_status(db: Session = Depends(get_db), user=Depends(require_permissions('catalog.view'))):
    return build_catalog_sync_status(setting_json(db, 'catalog_sync', default={}))


@router.post('/items')
def create_item(payload: CatalogItemCreate, db: Session = Depends(get_db), user=Depends(require_permissions('catalog.manage'))):
    try:
        return create_catalog_item(db, payload)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put('/items/{item_id}')
def update_item(item_id: int, payload: CatalogItemUpdate, db: Session = Depends(get_db), user=Depends(require_permissions('catalog.manage'))):
    try:
        return update_catalog_item(db, item_id, payload)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete('/items/{item_id}')
def remove_item(item_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('catalog.manage'))):
    try:
        return delete_catalog_item(db, item_id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/sync-from-accounting')
async def sync_from_accounting(db: Session = Depends(get_db), user=Depends(require_permissions('catalog.manage', 'sync.manage'))):
    try:
        result = await sync_catalog_from_accounting(db, force=True)
        result['ownership'] = build_catalog_sync_status(result)['ownership']
        result['transport'] = 'accounting_compatibility_api'
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
