from __future__ import annotations

PRIVILEGED_LEGACY_ROLES = {'owner', 'admin'}
PRIVILEGED_ROLE_CODES = {'owner'}


def is_privileged_role_name(value: str | None) -> bool:
    return str(value or '').strip().lower() in PRIVILEGED_LEGACY_ROLES


def role_codes_include_owner(values) -> bool:
    return bool({str(value or '').strip().lower() for value in (values or [])} & PRIVILEGED_ROLE_CODES)


def validate_user_admin_change(
    *,
    actor_user_id: int | None,
    target_user_id: int | None,
    actor_is_superuser: bool,
    target_is_superuser: bool = False,
    requested_legacy_role: str | None = None,
    requested_role_codes=None,
    requested_is_active: bool | None = None,
    authorization_fields_present: bool = False,
    sensitive_fields_present: bool = False,
) -> None:
    same_user = actor_user_id is not None and target_user_id is not None and int(actor_user_id) == int(target_user_id)
    if same_user and requested_is_active is False:
        raise ValueError('You cannot deactivate your own POS account.')
    if same_user and authorization_fields_present:
        raise ValueError('You cannot change your own roles or authorization through user administration.')

    grants_superuser = is_privileged_role_name(requested_legacy_role) or role_codes_include_owner(requested_role_codes)
    if grants_superuser and not actor_is_superuser:
        raise ValueError('Only an existing POS owner/admin may grant owner-level access.')
    if target_is_superuser and sensitive_fields_present and not actor_is_superuser:
        raise ValueError('Only an existing POS owner/admin may modify an owner/admin account.')


def safe_user_security_audit_details(*, changed_fields, role_ids=None, is_active=None) -> dict:
    changed = {str(field) for field in changed_fields if str(field)}
    details = {'changed_fields': sorted(changed - {'password'})}
    if 'password' in changed:
        details['password_changed'] = True
    if role_ids is not None:
        details['role_ids'] = [int(value) for value in role_ids]
    if is_active is not None:
        details['is_active'] = bool(is_active)
    return details
