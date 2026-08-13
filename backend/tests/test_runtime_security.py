import pytest

from app.core.settings import Settings


def make_settings(**overrides):
    base = {
        'environment': 'production',
        'secret_key': 's' * 48,
        'accounting_integration_secret': 'a' * 48,
        'integration_api_key': 'i' * 48,
        'allow_default_admin_bootstrap': False,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_safe_defaults_disable_bootstrap_and_do_not_ship_signing_secret():
    assert Settings.model_fields['secret_key'].default == ''
    assert Settings.model_fields['allow_default_admin_bootstrap'].default is False
    settings = Settings(
        _env_file=None,
        environment='development',
        secret_key='',
        allow_default_admin_bootstrap=False,
    )
    assert settings.bootstrap_enabled is False


def test_bootstrap_is_development_only_even_when_flag_enabled():
    assert make_settings(environment='production', allow_default_admin_bootstrap=True).bootstrap_enabled is False
    assert make_settings(environment='staging', allow_default_admin_bootstrap=True).bootstrap_enabled is False
    development = Settings(
        _env_file=None,
        environment='development',
        allow_default_admin_bootstrap=True,
        development_admin_username='local-owner',
        development_admin_password='local-owner-password-strong',
    )
    assert development.bootstrap_enabled is True


@pytest.mark.parametrize('environment', ['production', 'staging'])
def test_strict_environment_rejects_missing_or_placeholder_signing_secret(environment):
    missing = make_settings(environment=environment, secret_key='')
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        missing.validate_runtime_security()

    placeholder = make_settings(environment=environment, secret_key='change-me-super-secret')
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        placeholder.validate_runtime_security()


@pytest.mark.parametrize('environment', ['production', 'staging'])
def test_strict_environment_rejects_bootstrap_enabled(environment):
    settings = make_settings(environment=environment, allow_default_admin_bootstrap=True)
    with pytest.raises(RuntimeError, match='bootstrap'):
        settings.validate_runtime_security()


def test_disabled_integrations_do_not_require_credentials():
    settings = make_settings(
        inventory_integration_enabled=False,
        inventory_integration_token='',
        operations_integration_enabled=False,
        operations_integration_key='',
        staff_integration_enabled=False,
        staff_integration_key='',
    )
    settings.validate_runtime_security()


def test_enabled_integrations_require_credentials():
    inventory = make_settings(inventory_integration_enabled=True, inventory_integration_token='')
    with pytest.raises(RuntimeError, match='INVENTORY_INTEGRATION_TOKEN'):
        inventory.validate_runtime_security()

    operations = make_settings(operations_integration_enabled=True, operations_integration_key='')
    with pytest.raises(RuntimeError, match='OPERATIONS_INTEGRATION_KEY'):
        operations.validate_runtime_security()

    staff = make_settings(staff_integration_enabled=True, staff_integration_key='')
    with pytest.raises(RuntimeError, match='STAFF_INTEGRATION_KEY'):
        staff.validate_runtime_security()


def test_development_security_warnings_do_not_fail_startup_validation():
    settings = Settings(_env_file=None, environment='development', secret_key='')
    assert settings.security_warnings
    settings.validate_runtime_security()
