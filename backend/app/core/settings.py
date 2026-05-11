from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = BACKEND_ROOT / 'pos.db'


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
    secret_key: str = 'change-me-super-secret'
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    allow_default_admin_bootstrap: bool = True
    cors_origins: str = 'http://localhost:3001,http://127.0.0.1:3001'
    http_timeout_seconds: int = 20
    health_timeout_seconds: int = 5
    log_level: str = 'INFO'
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 240
    rate_limit_backend: str = 'redis'
    rate_limit_redis_prefix: str = 'dedicated-pos:ratelimit'
    redis_url: str = 'redis://redis:6379/0'
    startup_require_migrations: bool = True
    sync_worker_poll_seconds: int = 30
    sync_worker_batch_size: int = 25
    sync_worker_stale_seconds: int = 120
    trusted_proxy_depth: int = 0
    accounting_api_base: str = 'https://hiddenoasis.app/api'
    accounting_integration_secret: str = ''
    accounting_integration_token_path: str = '/auth/integration/token'
    trust_proxy_headers: bool = False
    model_config = SettingsConfigDict(env_file=str(BACKEND_ROOT / '.env'), extra='ignore')

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    @property
    def resolved_database_url(self) -> str:
        return _resolve_sqlite_url(self.database_url)

    @property
    def bootstrap_enabled(self) -> bool:
        if not self.allow_default_admin_bootstrap:
            return False
        return self.environment.strip().lower() != 'production'

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == 'production'


settings = Settings()
