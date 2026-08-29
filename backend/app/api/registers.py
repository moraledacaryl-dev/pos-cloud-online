import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.schemas.common import OutletCreate, OutletUpdate, RegisterCreate, RegisterUpdate
from app.services.pos_service import create_outlet, create_register, list_outlets, list_registers, update_outlet, update_register
from app.services.sync_service import fetch_accounting_financial_accounts, mapping_health_summary, validate_account_mapping

router = APIRouter()


def _integration_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            'code': 'integration_unavailable',
            'integration': 'accounting',
            'message': 'Accounting is temporarily unavailable. Local POS selling remains available; retry the mapping request shortly.',
        },
    )


@router.get('/outlets')
def outlets(db: Session = Depends(get_db), user=Depends(require_permissions('registers.view'))):
    return list_outlets(db)


@router.post('/outlets')
def add_outlet(payload: OutletCreate, db: Session = Depends(get_db), user=Depends(require_permissions('registers.manage'))):
    try:
        return create_outlet(db, payload)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put('/outlets/{outlet_id}')
def edit_outlet(outlet_id: int, payload: OutletUpdate, db: Session = Depends(get_db), user=Depends(require_permissions('registers.manage'))):
    try:
        return update_outlet(db, outlet_id, payload)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/accounting-accounts')
async def accounting_accounts(db: Session = Depends(get_db), user=Depends(require_permissions('registers.manage'))):
    try:
        return await fetch_accounting_financial_accounts(db)
    except httpx.RequestError as e:
        raise _integration_unavailable(e) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/accounting-accounts/validate')
async def accounting_accounts_validate(account_id: int | None = None, account_code: str | None = None, db: Session = Depends(get_db), user=Depends(require_permissions('registers.manage'))):
    try:
        return await validate_account_mapping(db, account_id=account_id, account_code=account_code)
    except httpx.RequestError as e:
        raise _integration_unavailable(e) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get('')
def registers(active_only: bool = False, db: Session = Depends(get_db), user=Depends(require_permissions('registers.view'))):
    return list_registers(db, only_active=active_only)


@router.post('')
async def add_register(payload: RegisterCreate, db: Session = Depends(get_db), user=Depends(require_permissions('registers.manage'))):
    try:
        if payload.accounting_financial_account_id or payload.accounting_financial_account_code:
            check = await validate_account_mapping(db, account_id=payload.accounting_financial_account_id, account_code=payload.accounting_financial_account_code)
            if not check.get('ok'):
                raise HTTPException(status_code=400, detail='Selected accounting drawer mapping is invalid.')
        return create_register(db, payload)
    except httpx.RequestError as e:
        raise _integration_unavailable(e) from e
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put('/{register_id}')
async def edit_register(register_id: int, payload: RegisterUpdate, db: Session = Depends(get_db), user=Depends(require_permissions('registers.manage'))):
    try:
        if payload.accounting_financial_account_id or payload.accounting_financial_account_code:
            check = await validate_account_mapping(db, account_id=payload.accounting_financial_account_id, account_code=payload.accounting_financial_account_code)
            if not check.get('ok'):
                raise HTTPException(status_code=400, detail='Selected accounting drawer mapping is invalid.')
        return update_register(db, register_id, payload)
    except httpx.RequestError as e:
        raise _integration_unavailable(e) from e
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/accounting-accounts/health')
async def accounting_accounts_health(db: Session = Depends(get_db), user=Depends(require_permissions('registers.manage'))):
    try:
        return await mapping_health_summary(db)
    except httpx.RequestError as e:
        raise _integration_unavailable(e) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
