import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = BACKEND_ROOT / 'pos.db'
DEFAULT_ACCOUNTING_API_BASE = 'https://accounting.hiddenoasis.app/api'
PLACEHOLDER_SECRET_MARKERS = (
    'change-me',
    'changeme',
    'replace',
    'placeholder',
    'local',
    'dev',
    'default',
    'example',
    'ci-',
)


def looks_like_placeholder_secret(value: str | None) -> bool:
    normalized = (value or '').strip().lower()
    if not normalized:
        return True
    compact = re.sub(r'[^a-z0-9]+', '', normalized)
    compact_markers = tuple(re.sub(r'[^a-z0-9]+', '', marker) for marker in PLACEHOLDER_SECRET_MARKERS)
    return (
        any(marker in normalized for marker in PLACEHOLDER_SECRET_MARKERS)
        or any(marker and marker in compact for marker in compact_markers)
        or len(normalized) < 16
    )


def is_supported_redis_url(value: str | None) -> bool:
    candidate = (value or '').strip()
    if not candidate:
        return False
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return False
    return parsed.scheme.lower() in {'redis', 'rediss'} and bool(parsed.hostname)


def _default_database_url() -> str:
    return f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


def _resolve_sqlite_url(url: str) -> str:
    prefix = 'sqlite:///./'
    if not url.startswith(prefix):
        return url
    relative_path = url[len(prefix):]
    resolved_path = (BACKEND_ROOT / relative_path).resolve()
    return f"sqlite:///{resolved_path.as_posix()}"


class Settings(BaseSettings):
    app_name: str = 'POS Cloud'
    environment: str = 'development'
    api_prefix: str = '/api'
    database_url: str = _default_database_url()
    secret_key: str = ''
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    allow_default_admin_bootstrap: bool = False
    development_admin_username: str = ''
    development_admin_password: str = ''
    cors_origins: str = 'http://localhost:3001,http://127.0.0.1:3001'
    http_timeout_seconds: int = 20
    health_timeout_seconds: int = 5
    log_level: str = 'INFO'
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 240
    rate_limit_backend: str = 'redis'
    rate_limit_redis_prefix: str = 'dedicated-pos:ratelimit'
    redis_url: str = 'redis://redis:6379/0'
    kds_stream_ticket_ttl_seconds: int = 30
    kds_stream_max_per_user: int = 4
    kds_stream_max_lifetime_seconds: int = 900
    startup_require_migrations: bool = True
    sync_worker_poll_seconds: int = 30
    sync_worker_batch_size: int = 25
    sync_worker_stale_seconds: int = 120
    accounting_api_base: str = DEFAULT_ACCOUNTING_API_BASE
    accounting_integration_secret: str = ''
    integration_api_key: str = ''
    accounting_integration_token_path: str = '/auth/integration/token'
    inventory_integration_enabled: bool = False
    inventory_api_base: str = 'https://inventory.hiddenoasis.app/api/v1'
    inventory_integration_token: str = ''
    inventory_pos_events_path: str = '/integrations/pos/events'
    operations_integration_enabled: bool = False
    operations_api_base: str = 'https://operations.hiddenoasis.app/api'
    operations_integration_key: str = ''
    operations_source_app: str = 'dedicated_pos_cloud'
    operations_integration_timeout_seconds: int = 5
    staff_integration_enabled: bool = False
    staff_integration_key: str = ''
    model_config = SettingsConfigDict(env_file=str(BACKEND_ROOT / '.env'), extra='ignore')

    @property
    def environment_name(self) -> str:
        return self.environment.strip().lower()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    @property
    def resolved_database_url(self) -> str:
        return _resolve_sqlite_url(self.database_url)

    @property
    def bootstrap_enabled(self) -> bool:
        return self.environment_name == 'development' and self.allow_default_admin_bootstrap

    @property
    def is_production(self) -> bool:
        return self.environment_name == 'production'

    @property
    def is_strict_environment(self) -> bool:
        return self.environment_name in {'production', 'staging'}

    @property
    def security_warnings(self) -> list[str]:
        warnings: list[str] = []
        if looks_like_placeholder_secret(self.secret_key) or len((self.secret_key or '').strip()) < 32:
            warnings.append('SECRET_KEY must be a non-placeholder signing value of at least 32 characters.')
        if looks_like_placeholder_secret(self.accounting_integration_secret):
            warnings.append('ACCOUNTING_INTEGRATION_SECRET is unset or still using a placeholder value.')
        if looks_like_placeholder_secret(self.integration_api_key):
            warnings.append('INTEGRATION_API_KEY is unset or still using a placeholder value.')
        if self.inventory_integration_enabled and looks_like_placeholder_secret(self.inventory_integration_token):
            warnings.append('INVENTORY_INTEGRATION_TOKEN is unset or still using a placeholder value.')
        if self.operations_integration_enabled and looks_like_placeholder_secret(self.operations_integration_key):
            warnings.append('OPERATIONS_INTEGRATION_KEY is unset or still using a placeholder value.')
        if self.staff_integration_enabled and looks_like_placeholder_secret(self.staff_integration_key):
            warnings.append('STAFF_INTEGRATION_KEY is unset or still using a placeholder value.')
        if self.is_strict_environment and self.allow_default_admin_bootstrap:
            warnings.append('Default admin bootstrap must be disabled in production and staging.')
        if self.is_strict_environment and self.rate_limit_enabled and self.rate_limit_backend.strip().lower() != 'redis':
            warnings.append('RATE_LIMIT_BACKEND must be redis in production and staging when rate limiting is enabled.')
        if self.is_strict_environment and self.rate_limit_enabled and not is_supported_redis_url(self.redis_url):
            warnings.append('REDIS_URL must use redis:// or rediss:// with a host in production and staging.')
        return warnings

    @property
    def runtime_security_errors(self) -> list[str]:
        if not self.is_strict_environment:
            return []
        return list(self.security_warnings)

    def validate_runtime_security(self) -> None:
        errors = self.runtime_security_errors
        if errors:
            raise RuntimeError('Unsafe runtime security configuration: ' + '; '.join(errors))


settings = Settings()
