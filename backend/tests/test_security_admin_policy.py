import pytest

from app.services.security_admin_policy import safe_user_security_audit_details, validate_user_admin_change


def test_non_superuser_cannot_grant_legacy_owner():
    with pytest.raises(ValueError, match='owner/admin'):
        validate_user_admin_change(
            actor_user_id=10,
            target_user_id=20,
            actor_is_superuser=False,
            requested_legacy_role='owner',
            authorization_fields_present=True,
            sensitive_fields_present=True,
        )


def test_non_superuser_cannot_attach_owner_role():
    with pytest.raises(ValueError, match='owner/admin'):
        validate_user_admin_change(
            actor_user_id=10,
            target_user_id=20,
            actor_is_superuser=False,
            requested_role_codes=['cashier', 'owner'],
            authorization_fields_present=True,
            sensitive_fields_present=True,
        )


def test_non_superuser_cannot_reset_or_disable_existing_owner():
    with pytest.raises(ValueError, match='modify an owner/admin'):
        validate_user_admin_change(
            actor_user_id=10,
            target_user_id=20,
            actor_is_superuser=False,
            target_is_superuser=True,
            sensitive_fields_present=True,
        )


def test_superuser_can_administer_privileged_accounts():
    validate_user_admin_change(
        actor_user_id=1,
        target_user_id=2,
        actor_is_superuser=True,
        target_is_superuser=True,
        requested_legacy_role='owner',
        requested_role_codes=['owner'],
        authorization_fields_present=True,
        sensitive_fields_present=True,
    )


def test_user_cannot_deactivate_self():
    with pytest.raises(ValueError, match='deactivate your own'):
        validate_user_admin_change(
            actor_user_id=7,
            target_user_id=7,
            actor_is_superuser=True,
            requested_is_active=False,
            sensitive_fields_present=True,
        )


def test_user_cannot_change_own_authorization():
    with pytest.raises(ValueError, match='own roles or authorization'):
        validate_user_admin_change(
            actor_user_id=7,
            target_user_id=7,
            actor_is_superuser=True,
            requested_legacy_role='manager',
            authorization_fields_present=True,
            sensitive_fields_present=True,
        )


def test_security_audit_never_contains_password_value():
    details = safe_user_security_audit_details(
        changed_fields={'password', 'role', 'is_active'},
        role_ids=[2, 3],
        is_active=False,
    )
    assert 'password' not in details['changed_fields']
    assert details['password_changed'] is True
    assert details['role_ids'] == [2, 3]
    assert details['is_active'] is False
    assert all('secret' not in str(value).lower() for value in details.values())
