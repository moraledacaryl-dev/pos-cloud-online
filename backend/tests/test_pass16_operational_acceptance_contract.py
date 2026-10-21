import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_staging_certification_refuses_production_target():
    script = read('scripts/pass16-staging-certify.sh')
    assert 'TARGET_ENVIRONMENT' in script
    assert "parsed.hostname.lower().rstrip('.') == 'pos.hiddenoasis.app'" in script
    assert 'refusing to run staging certification against production' in script
    assert 'PASS 16 STAGING AUTOMATED CERTIFICATION: PASS' in script


def test_restore_rehearsal_requires_explicit_non_production_guard():
    script = read('scripts/pass16-restore-rehearsal.sh')
    assert 'I_CONFIRM_NON_PRODUCTION_RESTORE_TARGET' in script
    assert 'hiddenoasis_pos_live' in script
    assert 'refusing a restore target that appears to be production' in script
    assert 'target public schema is not empty' in script
    assert 'RESTORE_ELAPSED_SECONDS=' in script


def test_final_acceptance_document_covers_audit_evidence_categories():
    document = read('docs/PASS_16_OPERATIONAL_ACCEPTANCE.md')
    required = [
        'Staging clone',
        'Backup restore and RTO/RPO',
        'Migration forward/rollback rehearsal',
        'Downstream staging contracts',
        'Physical peripheral acceptance',
        'Offline / dependency recovery',
        'Controlled live pilot',
        'Role acceptance',
        'Final audit rerun',
    ]
    for heading in required:
        assert heading in document
    assert 'Do not run it merely because the repository contains this checklist.' in document
    assert 'code/deployment certified with operational evidence pending' in document


def test_evidence_template_defaults_to_not_run_or_pending():
    template = read('docs/PASS_16_EVIDENCE_TEMPLATE.md')
    assert 'NOT RUN' in template
    assert 'OPERATIONAL ACCEPTANCE: PENDING / PASS / FAIL' in template
    assert 'Do not record passwords, API keys, card details' in template


def test_production_certifier_does_not_overclaim_operational_acceptance():
    script = read('scripts/production-certify.sh')
    assert 'docs/PASS_16_OPERATIONAL_ACCEPTANCE.md' in script
    assert 'proves the deployed code/runtime gate only' in script
    assert 'before declaring literal operational acceptance' in script


def test_restore_rehearsal_rejects_missing_revision_and_unsafe_database_urls(tmp_path):
    # Script must refuse risky targets before attempting any PostgreSQL connection.
    backup = tmp_path / 'placeholder.dump'
    backup.write_text('not-a-real-dump')
    script = ROOT / 'scripts' / 'pass16-restore-rehearsal.sh'
    base = {
        **os.environ,
        'BACKUP_FILE': str(backup),
        'NON_PRODUCTION_CONFIRM': 'I_CONFIRM_NON_PRODUCTION_RESTORE_TARGET',
        'EXPECTED_HEAD': '0013_generic_selling_rules',
        'TARGET_DATABASE_URL': 'postgresql://ci:ci@127.0.0.1:5432/pos_pass16_restore_ci',
    }

    def rejected(env, explanation):
        result = subprocess.run(
            ['bash', str(script)], cwd=ROOT, env={**base, **env},
            check=False, capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert explanation in result.stderr

    rejected({'EXPECTED_HEAD': ''}, 'EXPECTED_HEAD must explicitly match')
    rejected({'NON_PRODUCTION_CONFIRM': ''}, 'NON_PRODUCTION_CONFIRM')
    rejected({'TARGET_DATABASE_URL': 'postgresql://ci:ci@127.0.0.1:5432/hiddenoasis_pos_live'},
             'refusing a restore target')
    rejected({'TARGET_DATABASE_URL': 'postgresql://ci:ci@127.0.0.1:5432/pos_ci'},
             'refusing a restore target')
    rejected({'TARGET_DATABASE_URL': 'postgresql://ci:ci@db.example.com:5432/pos_pass16_restore_ci'},
             'refusing a restore target')
    rejected({'TARGET_DATABASE_URL': 'postgresql://ci:ci@127.0.0.1:5432/pos_pass16_restore_ci?service=other'},
             'refusing a restore target')


def test_isolated_restore_workflow_remains_synthetic_and_uses_no_production_environment():
    workflow = read('.github/workflows/pass16-restore-ci.yml')
    assert 'postgres:16' in workflow
    assert 'pos_pass16_source' in workflow
    assert 'pos_pass16_restore_ci' in workflow
    assert 'EXPECTED_HEAD: 0013_generic_selling_rules' in workflow
    assert 'PASS 16 NON-PRODUCTION RESTORE REHEARSAL: PASS' in workflow
    assert 'pg_dump' in workflow and 'pg_restore --list' in workflow
    assert 'PASS16_SYNTHETIC_RESTORE=1 python backend/scripts/pass16_synthetic_financial_restore.py seed' in workflow
    assert 'PASS16_SYNTHETIC_RESTORE=1 python backend/scripts/pass16_synthetic_financial_restore.py verify' in workflow
    fixture = read('backend/scripts/pass16_synthetic_financial_restore.py')
    assert 'sync_outbox_events' in fixture and 'pos_order_payments' in fixture
    assert 'cash_movements' in fixture and 'audit_logs' in fixture
    assert 'PASS16_SYNTHETIC_FINANCIAL_RECONCILIATION=PASS' in fixture


def test_financial_restore_fixture_rejects_execution_outside_github_ci():
    fixture = ROOT / 'backend/scripts/pass16_synthetic_financial_restore.py'
    env = {
        **os.environ,
        'ENVIRONMENT': 'test',
        'PASS16_SYNTHETIC_RESTORE': '1',
        'GITHUB_ACTIONS': 'false',
        'DATABASE_URL': 'postgresql+psycopg://pos:pos@127.0.0.1:5432/pos_pass16_source',
        'TARGET_DATABASE_URL': 'postgresql://pos:pos@127.0.0.1:5432/pos_pass16_restore_ci',
    }
    completed = subprocess.run(
        ['python', str(fixture), 'seed'],
        env=env, cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode != 0
    assert 'restricted to the isolated GitHub CI drill' in completed.stderr


def test_staging_certification_cannot_skip_migration_or_real_runtime_checks():
    script = read('scripts/pass16-staging-certify.sh')
    assert 'EXPECTED_COMMIT must be an explicit full 40-character SHA' in script
    assert '/internal/healthz/details' in script
    assert "report.get('environment') != 'staging'" in script
    assert 'staging migration verification cannot be skipped' in script
    assert 'staging Alembic schema drift' in script
    assert 'public gateway hides private health diagnostics' in script
    assert 'PUBLIC_API_PREFIX' in script


def test_staging_workflow_uses_disposable_dependencies_and_actual_runtime():
    workflow = read('.github/workflows/pass16-staging-ci.yml')
    assert 'postgres:16' in workflow and 'redis:7' in workflow
    assert 'pos_pass16_staging_ci' in workflow
    assert 'ENVIRONMENT: staging' in workflow
    assert 'python -m app.workers.sync_worker' in workflow
    assert 'npm run build' in workflow
    assert 'bash scripts/pass16-staging-certify.sh' in workflow
    assert 'PASS 16 STAGING AUTOMATED CERTIFICATION: PASS' in workflow
    assert 'POS.HIDDENOASIS.APP:443' in workflow


def test_staging_certification_rejects_invalid_inputs_without_http_calls():
    script = ROOT / 'scripts/pass16-staging-certify.sh'
    base = {
        **os.environ,
        'TARGET_ENVIRONMENT': 'staging',
        'APP_DIR': str(ROOT),
        'PUBLIC_BASE': 'http://127.0.0.1:8080',
        'BACKEND_BASE': 'http://127.0.0.1:8100',
        'EXPECTED_COMMIT': '0' * 40,
    }

    def rejected(overrides, message):
        result = subprocess.run(
            ['bash', str(script)], cwd=ROOT, env={**base, **overrides},
            check=False, capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert message in result.stderr

    rejected({'EXPECTED_COMMIT': ''}, 'EXPECTED_COMMIT must be')
    rejected({'TARGET_ENVIRONMENT': 'production'}, 'TARGET_ENVIRONMENT must')
    rejected({'PUBLIC_API_PREFIX': '/internal'}, 'PUBLIC_API_PREFIX must')
    rejected({'PUBLIC_BASE': 'https://POS.HIDDENOASIS.APP:443'},
             'refusing to run staging certification against production')
    rejected({'BACKEND_BASE': 'https://pos.hiddenoasis.app:443'},
             'refusing to run staging certification against production')


def test_accounting_http_replay_ci_is_isolated_and_verifies_ambiguous_ack():
    workflow = read('.github/workflows/pass16-accounting-replay-ci.yml')
    assert 'pos_pass16_accounting_ci' in workflow
    assert 'postgres:16' in workflow
    assert 'PASS16_ACCOUNTING_REPLAY_CI' in workflow
    assert 'pass16_accounting_replay.py' in workflow
    assert 'PASS16_ACCOUNTING_LOST_ACK_IDEMPOTENT_REPLAY=PASS' in workflow

    script = read('backend/scripts/pass16_accounting_replay.py')
    assert 'pass16-replay-order-' in script
    assert 'run_outbox_sync(db, limit=' in script
    assert 'PASS16_ACCOUNTING_OUTAGE_RECOVERY=PASS' in script
    assert 'PASS16_ACCOUNTING_HTTP_REPLAY_CERTIFICATION=PASS' in script
    stub = read('backend/scripts/pass16_accounting_replay_stub.py')
    assert '"fail_before_accept"' in stub
    assert '"accept_then_503"' in stub
    assert 'ORDERS[external_id] = data' in stub
    assert 'unexpected synthetic Accounting route' in stub


def test_accounting_replay_stub_rejects_non_ci_execution():
    script = ROOT / 'backend/scripts/pass16_accounting_replay_stub.py'
    result = subprocess.run(
        ['python', str(script)],
        cwd=ROOT,
        env={**os.environ, 'GITHUB_ACTIONS': 'false',
             'PASS16_ACCOUNTING_REPLAY_CI': '1', 'ENVIRONMENT': 'staging'},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert 'requires isolated staging CI' in result.stderr


def test_inventory_http_replay_is_a_disposable_real_transport_contract():
    workflow = read('.github/workflows/pass16-inventory-replay-ci.yml')
    runner = read('backend/scripts/pass16_inventory_replay.py')
    receiver = read('backend/scripts/pass16_inventory_replay_stub.py')
    assert 'postgres:16' in workflow
    assert 'pos_pass16_inventory_ci' in workflow
    assert 'INVENTORY_API_BASE: http://127.0.0.1:18992/api/v1' in workflow
    assert 'INVENTORY_INTEGRATION_ENABLED:' in workflow
    assert 'pass16_inventory_replay.py' in workflow
    assert 'PASS16_INVENTORY_HTTP_REPLAY_CERTIFICATION' in workflow
    assert 'run_inventory_outbox_sync(db, limit=limit)' in runner
    assert 'enqueue_inventory_event(db, original, "sale_completed"' in runner
    assert 'enqueue_inventory_event(db, modified, "sale_voided"' in runner
    assert 'PASS16_INVENTORY_REVERSAL_WAITS_FOR_SALE=PASS' in runner
    assert 'PASS16_INVENTORY_LOST_ACK_IDEMPOTENT_REPLAY=PASS' in runner
    assert 'PASS16_INVENTORY_ORIGINAL_SKU_REVERSAL=PASS' in runner
    assert 'external_event_id' in receiver
    assert 'STOCK_DELTAS' in receiver
    assert '"accept_then_503"' in receiver
    assert 'X-Integration-Token' in receiver
    assert 'unexpected synthetic Inventory route' in receiver


def test_inventory_http_receiver_refuses_non_ci_execution():
    receiver = ROOT / 'backend/scripts/pass16_inventory_replay_stub.py'
    result = subprocess.run(
        ['python', str(receiver)], cwd=ROOT,
        env={**os.environ, 'GITHUB_ACTIONS': 'false',
             'PASS16_INVENTORY_REPLAY_CI': '1', 'ENVIRONMENT': 'staging'},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert 'restricted to isolated staging CI' in result.stderr
