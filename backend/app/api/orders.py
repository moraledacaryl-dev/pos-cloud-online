from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.core.settings import settings
from app.db.database import get_db
from app.models.entities import PosOrder
from app.schemas.common import (
    OrderCreate,
    OrderPayPayload,
    OrderTableMergePayload,
    OrderTableTransferPayload,
    OrderUpdate,
    OrderVoidPayload,
    RefundCreate,
)
from app.services.approval_guard import consume_protected_approval, reject_legacy_client_approver
from app.services.inventory_integration import (
    enqueue_inventory_event,
    should_reverse_inventory_for_refund,
    should_reverse_inventory_for_void,
)
from app.services.operations_integration import publish_operations_event
from app.services.order_state_policy import assert_order_action, policy_snapshot
from app.services.payment_control_policy import validate_payment_control
from app.services.pos_service import (
    create_order,
    create_refund,
    get_order,
    list_orders,
    list_refunds,
    merge_order_table,
    pay_order,
    set_order_status,
    transfer_order_table,
    update_order,
    void_order,
)

router = APIRouter()


def _assert_order_action(db: Session, order_id: int, action: str) -> PosOrder:
    row = db.get(PosOrder, int(order_id))
    if not row:
        raise ValueError('Order not found.')
    assert_order_action(row.status, action)
    return row


def _has_discount(payload) -> bool:
    return any(float(getattr(line, 'discount_amount', 0) or 0) > 0.009 for line in (getattr(payload, 'lines', None) or []))


@router.get('/state-policy')
def state_policy(user=Depends(require_permissions('pos.use'))):
    return policy_snapshot()


@router.get('')
def orders(status: str | None = None, session_id: int | None = None, q: str | None = None, business_date: str | None = None, limit: int = 200, db: Session = Depends(get_db), user=Depends(require_permissions('pos.use'))):
    return list_orders(db, status=status, session_id=session_id, q=q, business_date=business_date, limit=limit)


@router.get('/{order_id}')
def order_detail(order_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('pos.use'))):
    try:
        return get_order(db, order_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post('')
def add_order(payload: OrderCreate, db: Session = Depends(get_db), current_user=Depends(require_permissions('orders.manage'))):
    try:
        reject_legacy_client_approver(payload)
        if _has_discount(payload):
            with consume_protected_approval(
                db,
                requester=current_user,
                payload=payload,
                approval_type='discount',
                entity_type='order',
                entity_id=None,
                requested_reason='Discounted order creation',
            ):
                return create_order(db, payload, user_id=getattr(current_user, 'id', None))
        return create_order(db, payload, user_id=getattr(current_user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put('/{order_id}')
def edit_order(order_id: int, payload: OrderUpdate, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        reject_legacy_client_approver(payload)
        _assert_order_action(db, order_id, 'edit')
        if _has_discount(payload):
            with consume_protected_approval(
                db,
                requester=user,
                payload=payload,
                approval_type='discount',
                entity_type='order',
                entity_id=order_id,
                requested_reason='Discounted order update',
            ):
                return update_order(db, order_id, payload, user_id=getattr(user, 'id', None))
        return update_order(db, order_id, payload, user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/hold')
def hold_order(order_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        _assert_order_action(db, order_id, 'hold')
        return set_order_status(db, order_id, 'held', user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/resume')
def resume_order(order_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        _assert_order_action(db, order_id, 'resume')
        return set_order_status(db, order_id, 'draft', user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/pay')
def settle_order(order_id: int, payload: OrderPayPayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user=Depends(require_permissions('orders.manage'))):
    try:
        _assert_order_action(db, order_id, 'pay')
        order_snapshot = get_order(db, order_id)
        validate_payment_control(order_snapshot, payload.payments)
        result = pay_order(db, order_id, payload, user_id=getattr(current_user, 'id', None))
        if settings.inventory_integration_enabled:
            enqueue_inventory_event(db, result, 'sale_completed')
        background_tasks.add_task(
            publish_operations_event,
            'order.finalized',
            f'order-finalized:{order_id}',
            title=f'POS order finalized #{order_id}',
            summary='A POS order was finalized.',
            payload={'order': result},
            subject_type='order',
            subject_id=order_id,
            external_user_id=getattr(current_user, 'id', None),
        )
        return result
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/transfer-table')
def transfer_table(order_id: int, payload: OrderTableTransferPayload, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        _assert_order_action(db, order_id, 'transfer_table')
        return transfer_order_table(db, order_id, payload.target_table_label, target_service_area=payload.target_service_area, user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/merge-table')
def merge_table(order_id: int, payload: OrderTableMergePayload, db: Session = Depends(get_db), user=Depends(require_permissions('orders.manage'))):
    try:
        _assert_order_action(db, order_id, 'merge_table')
        return merge_order_table(db, order_id, payload.target_table_label, target_service_area=payload.target_service_area, user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{order_id}/void')
def cancel_order(order_id: int, payload: OrderVoidPayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user=Depends(require_permissions('orders.void'))):
    try:
        _assert_order_action(db, order_id, 'void')
        pre_void = get_order(db, order_id)
        with consume_protected_approval(
            db,
            requester=current_user,
            payload=payload,
            approval_type='void',
            entity_type='order',
            entity_id=order_id,
            requested_reason=payload.reason,
        ) as grant:
            result = void_order(db, order_id, payload.reason, user_id=getattr(current_user, 'id', None), approved_by_user_id=grant['approved_by_user_id'])
        if settings.inventory_integration_enabled and should_reverse_inventory_for_void(pre_void):
            enqueue_inventory_event(db, result, 'sale_voided')
        background_tasks.add_task(
            publish_operations_event,
            'void.review_needed',
            f'void-review:{order_id}',
            title=f'POS void requires review #{order_id}',
            summary=payload.reason,
            priority='High',
            payload={'order': result, 'reason': payload.reason},
            subject_type='order',
            subject_id=order_id,
            external_user_id=getattr(current_user, 'id', None),
        )
        return result
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
def refund_order(order_id: int, payload: RefundCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user=Depends(require_permissions('orders.manage'))):
    try:
        _assert_order_action(db, order_id, 'refund')
        with consume_protected_approval(
            db,
            requester=current_user,
            payload=payload,
            approval_type='refund',
            entity_type='refund',
            entity_id=order_id,
            requested_reason=payload.reason_text or payload.reason_code or 'Refund',
        ):
            result = create_refund(db, order_id, payload, cashier_user_id=getattr(current_user, 'id', None))
        order_after_refund = get_order(db, order_id)
        if settings.inventory_integration_enabled and should_reverse_inventory_for_refund(order_after_refund):
            enqueue_inventory_event(db, order_after_refund, 'sale_refunded')
        refund_id = result.get('id') if isinstance(result, dict) else getattr(result, 'id', order_id)
        background_tasks.add_task(
            publish_operations_event,
            'refund.review_needed',
            f'refund-review:{refund_id}',
            title=f'POS refund requires review #{refund_id}',
            summary='A POS refund was created.',
            priority='High',
            payload={'refund': result, 'order_id': order_id},
            subject_type='refund',
            subject_id=refund_id,
            external_user_id=getattr(current_user, 'id', None),
        )
        return result
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
