# Phase 6 Validation

This build hardens the attached full application without removing existing business features.

## Included hardening
- migration-first startup: runtime `create_all()` removed
- startup checks now require Alembic head before app boot
- production systemd setup runs `alembic upgrade head` before backend start
- production config now expects PostgreSQL and Redis
- live `.env` files are removed from the distributable package
- refresh-token rotation now respects user session versioning
- access tokens now carry session version and issued-at metadata
- forced logout / revoke-all sessions now invalidate both refresh and access tokens
- rate limiting now supports Redis-backed shared counters
- health details now expose DB, migration, rate limit, accounting reachability, sync-worker heartbeat, and outbox backlog

## Operational notes
- run `alembic upgrade head` before local app startup if `STARTUP_REQUIRE_MIGRATIONS=true`
- for production, configure `RATE_LIMIT_BACKEND=redis` and `REDIS_URL`
- sync worker heartbeat is stored in `system_settings` under `sync_worker_heartbeat`
