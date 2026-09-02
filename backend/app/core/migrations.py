from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from alembic import command
from app.core.settings import settings


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_alembic_config() -> Config:
    backend_root = _backend_root()
    config = Config(str(backend_root / 'alembic.ini'))
    config.set_main_option('script_location', str(backend_root / 'alembic'))
    config.set_main_option('sqlalchemy.url', settings.resolved_database_url)
    return config


def get_expected_heads() -> list[str]:
    script = ScriptDirectory.from_config(get_alembic_config())
    return list(script.get_heads())


def get_current_revisions(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    if 'alembic_version' not in inspector.get_table_names():
        return []
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT version_num FROM alembic_version')).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def migration_status(engine: Engine) -> dict:
    current = sorted(get_current_revisions(engine))
    expected = sorted(get_expected_heads())
    return {
        'ok': current == expected and bool(expected),
        'current_revisions': current,
        'expected_heads': expected,
        'requires_upgrade': current != expected,
    }


def ensure_database_at_head(engine: Engine):
    if not settings.startup_require_migrations:
        return
    status = migration_status(engine)
    if not status['ok']:
        raise RuntimeError(
            'Database is not at Alembic head. Run "alembic upgrade head" before starting the application. '
            f"Current revisions: {status['current_revisions']} Expected heads: {status['expected_heads']}"
        )


def upgrade_database_to_head():
    command.upgrade(get_alembic_config(), 'head')


def ensure_database_ready(engine: Engine):
    if not settings.startup_require_migrations:
        return
    try:
        status = migration_status(engine)
    except Exception as exc:
        raise RuntimeError(
            'Database connection failed during startup. '
            'Verify DATABASE_URL points to a running database.'
        ) from exc
    if status['ok']:
        return
    if settings.is_production:
        raise RuntimeError(
            'Database is not at Alembic head. Run "alembic upgrade head" before starting the application. '
            f"Current revisions: {status['current_revisions']} Expected heads: {status['expected_heads']}"
        )
    upgrade_database_to_head()
    ensure_database_at_head(engine)
