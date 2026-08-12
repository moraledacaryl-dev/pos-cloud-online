from __future__ import annotations

PRIVILEGED_LEGACY_ROLES = {'owner', 'admin'}
PRIVILEGED_ROLE_CODES = {'owner'}


def is_privileged_role_name(value: str | None) -> bool:
    return str(value or '').strip().lower() in PRIVILEGED_LEGACY_ROLES


def validate_user_admin_change(
    *,
    actor_user_id: int | None,
    target_user_id: int | None,
    actor_is_superuser: bool,
    requested_legacy_role: str | None = None,
    requested_role_codes: list[str] | tuple[str, ...] | set[str] | None = None,
    requested_is_active: bool | None = None,
    authorization_fields_present: bool = False,
) -> None:
    """Guard privileged user-management mutations.

    `users.manage` permits ordinary account administration, but only an existing
    superuser may grant the legacy owner/admin role or attach the canonical
    Owner RBAC role. A user also cannot alter their own authorization envelope
    or deactivate themselves through the admin endpoint.
    """

    same_user = actor_user_id is not None and target_user_id is not None and int(actor_user_id) == int(target_user_id)

    if same_user and requested_is_active is False:
        raise ValueError('You cannot deactivate your own POS account.')

    if same_user and authorization_fields_present:
        raise ValueError('You cannot change your own roles or authorization through user administration.')

    requested_codes = {str(code or '').strip().lower() for code in (requested_role_codes or []) if str(code or '').strip()}
    grants_superuser = is_privileged_role_name(requested_legacy_role) or bool(requested_codes & PRIVILEGED_ROLE_CODES)
    if grants_superuser and not actor_is_superuser:
        raise ValueError('Only an existing POS owner/admin may grant owner-level access.')


def safe_user_security_audit_details(*, changed_fields: list[str] | set[str] | tuple[str, ...], role_ids=None, is_active=None) -> dict:
    """Build audit-safe metadata without ever serializing password material."""
    fields = sorted({str(field) for field in changed_fields if str(field) and str(field) != 'password'})
    details = {'changed_fields': fields}
    if 'password' in set(changed_fields):
        details['password_changed'] = True
    if role_ids is not None:
        details['role_ids'] = [int(value) for value in role_ids]
    if is_active is not None:
        details['is_active'] = bool(is_active)
    return details
