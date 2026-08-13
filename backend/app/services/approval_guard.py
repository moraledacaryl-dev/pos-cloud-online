from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.models.entities import User
from app.services.approval_service import (
    approve_grant,
    consume_approval_grant,
    request_approval,
    reset_active_consumed_grant,
    set_active_consumed_grant,
    user_can_manage_approvals,
)


def protected_payload(payload) -> dict:
    if hasattr(payload, 'model_dump'):
        data = payload.model_dump(exclude_none=True, exclude_unset=True)
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        data = {}
    data.pop('approved_by_user_id', None)
    data.pop('approval_grant_uuid', None)
    return data


def reject_legacy_client_approver(payload) -> None:
    if getattr(payload, 'approved_by_user_id', None) is not None:
        raise ValueError('Client-supplied approved_by_user_id is not accepted. Use a server-verified manager approval grant.')


def _self_authorized_grant(
    db: Session,
    *,
    requester: User,
    approval_type: str,
    entity_type: str,
    entity_id: str | int | None,
    requested_reason: str | None,
    protected: dict,
) -> dict:
    if not user_can_manage_approvals(db, requester):
        raise ValueError('Manager approval is required before this action can be completed.')
    grant = request_approval(
        db,
        approval_type=approval_type,
        entity_type=entity_type,
        entity_id=entity_id,
        requested_by_user_id=requester.id,
        requested_reason=requested_reason,
        protected_payload=protected,
        commit=False,
    )
    return approve_grant(db, grant['id'], requester, decision_note='Authenticated manager self-action', commit=False)


@contextmanager
def consume_protected_approval(
    db: Session,
    *,
    requester: User,
    payload,
    approval_type: str,
    entity_type: str,
    entity_id: str | int | None,
    requested_reason: str | None = None,
):
    reject_legacy_client_approver(payload)
    protected = protected_payload(payload)
    approval_uuid = getattr(payload, 'approval_grant_uuid', None)
    if approval_uuid:
        grant = consume_approval_grant(
            db,
            approval_uuid=approval_uuid,
            requester_user_id=requester.id,
            approval_type=approval_type,
            entity_type=entity_type,
            entity_id=entity_id,
            protected_payload=protected,
        )
    else:
        approved = _self_authorized_grant(
            db,
            requester=requester,
            approval_type=approval_type,
            entity_type=entity_type,
            entity_id=entity_id,
            requested_reason=requested_reason,
            protected=protected,
        )
        grant = consume_approval_grant(
            db,
            approval_uuid=approved['approval_uuid'],
            requester_user_id=requester.id,
            approval_type=approval_type,
            entity_type=entity_type,
            entity_id=entity_id,
            protected_payload=protected,
        )

    # Internal compatibility only: existing POS service signatures still carry an
    # approver ID, but it is populated exclusively from the consumed server grant.
    setattr(payload, 'approved_by_user_id', grant['approved_by_user_id'])
    token = set_active_consumed_grant(grant)
    try:
        yield grant
    finally:
        reset_active_consumed_grant(token)
