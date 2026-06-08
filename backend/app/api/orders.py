from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.schemas.common import OrderCreate, OrderPayPayload, OrderTableMergePayload, OrderTableTransferPayload, OrderUpdate, OrderVoidPayload, RefundCreate
from app.services.pos_service import create_order, create_refund, get_order, list_orders, list_refunds, merge_order_table, pay_order, set_order_status, transfer_order_table, update_order, void_order

router = APIRouter()


@router.get('/')
def orders(status: str | None = None, session_id: int | None = None, q: str | None = None, business_date: str | None = None, limit: int = 200, db: Session = Depends(get_db), user=Depends(require_permissions('pos.use'))):
    return list_orders(db, status=status, session_id=session_id, q=q, business_date=business_date, limit=limit)


@router.get('/{order_id}')
def order_detail(order_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('pos.use'))):
    try:
        return get_order(db, order_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post('/')
def add_order(payload: OrderCreate, db: Session = Depends(get_db), current_user=Depends(require_permissions('orders.manage'))):
    try:
        return create_order(db, payload, user_id=getattr(current_user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put('/{order_id}')
def edit_order(order_id: int, payload: OrderUpdate, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        return update_order(db, order_id, payload, user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/hold')
def hold_order(order_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        return set_order_status(db, order_id, 'held', user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/resume')
def resume_order(order_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        return set_order_status(db, order_id, 'draft', user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/pay')
def settle_order(order_id: int, payload: OrderPayPayload, db: Session = Depends(get_db), current_user=Depends(require_permissions('orders.manage'))):
    try:
        return pay_order(db, order_id, payload, user_id=getattr(current_user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/transfer-table')
def transfer_table(order_id: int, payload: OrderTableTransferPayload, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        return transfer_order_table(db, order_id, payload.target_table_label, target_service_area=payload.target_service_area, user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/merge-table')
def merge_table(order_id: int, payload: OrderTableMergePayload, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        return merge_order_table(db, order_id, payload.target_table_label, target_service_area=payload.target_service_area, user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/void')
def cancel_order(order_id: int, payload: OrderVoidPayload, db: Session = Depends(get_db), current_user=Depends(require_permissions('orders.void'))):
    try:
        return void_order(db, order_id, payload.reason, user_id=getattr(current_user, 'id', None), approved_by_user_id=payload.approved_by_user_id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/{order_id}/refunds')
def order_refunds(order_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        return list_refunds(db, order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/refunds')
def refund_order(order_id: int, payload: RefundCreate, db: Session = Depends(get_db), current_user=Depends(require_permissions('orders.manage'))):
    try:
        return create_refund(db, order_id, payload, cashier_user_id=getattr(current_user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
