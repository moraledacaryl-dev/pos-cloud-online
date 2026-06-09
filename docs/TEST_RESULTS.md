# Test Results

Date: 2026-06-09

## POS

- Command: `PYTHONPYCACHEPREFIX=/tmp/pycache-pos python3 -m compileall backend/app/core/settings.py backend/app/services/pos_service.py backend/app/services/sync_service.py backend/tests/test_staff_readiness.py frontend/app/settings/page.js`
  - Result: passed
  - Details: Accounting API default, startup repair code, sync service, and adjusted tests compile.
- Command: `PYTHONPATH=backend PYTHONPYCACHEPREFIX=/tmp/pycache-pos python3 - <<'PY' ...`
  - Result: not run
  - Reason: this local shell has no `pydantic_settings` and no `sqlalchemy`, so runtime import smoke checks cannot execute here.
  - Classification: environment/dependency gap, not a code failure.
- Command: `PYTHONPYCACHEPREFIX=/tmp/pycache-pos python3 -m pytest backend/tests/test_staff_readiness.py`
  - Result: not run
  - Reason: this local shell has no `pytest` module.
  - Classification: environment/dependency gap, not a code failure.
- Command: `PYTHONPYCACHEPREFIX=/tmp/pycache-pos python3 -m compileall backend/app/core/settings.py backend/app/api/reports.py backend/tests/test_daily_ops_context.py`
  - Result: passed
  - Details: daily operations context route, settings, and tests compile after integration-key hardening.
- Command: `PYTHONPYCACHEPREFIX=/tmp/pycache-pos python3 -m pytest backend/tests/test_daily_ops_context.py`
  - Result: not run
  - Reason: this local shell has no `pytest` module.
  - Classification: environment/dependency gap, not a code failure.
- Command: `node --version` / frontend build
  - Result: not run
  - Reason: this local shell has no `node`/`npm`.
  - Classification: environment/dependency gap.

Next action: install backend/frontend dependencies in the POS environment, then run POS pytest, `npm run build`, `npm run test:smoke`, and `npm run test:ui`.
