from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core import rate_limit
from app.core.settings import Settings, looks_like_placeholder_secret
from app.core.settings import settings as runtime_settings

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_SAMPLE = ROOT / '.env.production.example'


def make_settings(**overrides):
    base = {
        'environment': 'production',
        'secret_key': 's' * 48,
        'accounting_integration_secret': 'a' * 48,
        'integration_api_key': 'i' * 48,
        'allow_default_admin_bootstrap': False,
        'rate_limit_enabled': True,
        'rate_limit_backend': 'redis',
        'redis_url': 'redis://127.0.0.1:6379/0',
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _parse_env_sample(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


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


@pytest.mark.parametrize(
    'value',
    [
        'CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32',
        'CHANGE_ME_SHARED_CROSS_APP_INTEGRATION_API_KEY',
        'CHANGE-ME-SHARED-POS-ACCOUNTING-INTEGRATION-SECRET',
        'change_me_pos_inventory_integration_token',
    ],
)
def test_placeholder_detection_normalizes_common_separators(value):
    assert looks_like_placeholder_secret(value) is True


def test_production_sample_placeholders_are_parsed_and_rejected_literally():
    sample = _parse_env_sample(PRODUCTION_SAMPLE)
    placeholders = {
        key: value
        for key, value in sample.items()
        if 'CHANGE_ME' in value.upper() or 'CHANGE-ME' in value.upper()
    }
    assert placeholders, 'production sample must contain explicit replacement placeholders'
    assert all(looks_like_placeholder_secret(value) for value in placeholders.values())

    configured = make_settings(
        secret_key=sample['SECRET_KEY'],
        integration_api_key=sample['INTEGRATION_API_KEY'],
        accounting_integration_secret=sample['ACCOUNTING_INTEGRATION_SECRET'],
        inventory_integration_enabled=True,
        inventory_integration_token=sample['INVENTORY_INTEGRATION_TOKEN'],
        operations_integration_enabled=True,
        operations_integration_key=sample['OPERATIONS_INTEGRATION_KEY'],
    )
    with pytest.raises(RuntimeError):
        configured.validate_runtime_security()


def test_production_sample_uses_canonical_backend_port():
    sample = _parse_env_sample(PRODUCTION_SAMPLE)
    assert sample['PORT'] == '8100'


@pytest.mark.parametrize('environment', ['production', 'staging'])
def test_strict_environment_rejects_documented_sample_secret(environment):
    settings = make_settings(
        environment=environment,
        secret_key='CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32',
    )
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        settings.validate_runtime_security()


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


@pytest.mark.parametrize('environment', ['production', 'staging'])
def test_strict_environment_rejects_memory_rate_limiting(environment):
    settings = make_settings(environment=environment, rate_limit_backend='memory')
    with pytest.raises(RuntimeError, match='RATE_LIMIT_BACKEND'):
        settings.validate_runtime_security()


@pytest.mark.parametrize('environment', ['production', 'staging'])
def test_strict_environment_requires_redis_url_for_rate_limiting(environment):
    settings = make_settings(environment=environment, rate_limit_backend='redis', redis_url='')
    with pytest.raises(RuntimeError, match='REDIS_URL'):
        settings.validate_runtime_security()


@pytest.mark.parametrize('environment', ['production', 'staging'])
@pytest.mark.parametrize(
    'redis_url',
    [
        'http://127.0.0.1:6379/0',
        'postgresql://127.0.0.1:6379/0',
        'redis:///0',
        'not-a-url',
    ],
)
def test_strict_environment_rejects_invalid_redis_url_scheme_or_host(environment, redis_url):
    settings = make_settings(environment=environment, redis_url=redis_url)
    with pytest.raises(RuntimeError, match='REDIS_URL'):
        settings.validate_runtime_security()


@pytest.mark.parametrize('redis_url', ['redis://127.0.0.1:6379/0', 'rediss://cache.example.test:6380/0'])
def test_strict_environment_accepts_supported_redis_url_schemes(redis_url):
    make_settings(redis_url=redis_url).validate_runtime_security()


class _UnavailableRedis:
    def incr(self, _key):
        raise ConnectionError('redis unavailable')


@pytest.mark.parametrize('environment', ['production', 'staging'])
def test_strict_environment_rate_limiter_fails_closed_when_redis_is_lost(monkeypatch, environment):
    monkeypatch.setattr(runtime_settings, 'environment', environment)
    monkeypatch.setattr(runtime_settings, 'rate_limit_enabled', True)
    monkeypatch.setattr(rate_limit, '_BACKEND', 'redis')
    monkeypatch.setattr(rate_limit, '_REDIS_CLIENT', _UnavailableRedis())

    with pytest.raises(HTTPException) as exc:
        rate_limit.enforce_rate_limit('login:strict-fail-closed', limit=2, window_seconds=60)
    assert exc.value.status_code == 503


def test_staging_does_not_fall_back_to_memory_when_redis_package_is_missing(monkeypatch):
    monkeypatch.setattr(runtime_settings, 'environment', 'staging')
    monkeypatch.setattr(runtime_settings, 'rate_limit_enabled', True)
    monkeypatch.setattr(runtime_settings, 'rate_limit_backend', 'redis')
    monkeypatch.setattr(runtime_settings, 'redis_url', 'redis://127.0.0.1:6379/0')
    monkeypatch.setattr(rate_limit, 'redis', None)

    with pytest.raises(RuntimeError, match='redis package'):
        rate_limit.init_rate_limiter()


def test_development_security_warnings_do_not_fail_startup_validation():
    settings = Settings(_env_file=None, environment='development', secret_key='')
    assert settings.security_warnings
    settings.validate_runtime_security()
