import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github' / 'workflows' / 'production-equivalent-ci.yml'
DEPLOY_WORKFLOW = ROOT / '.github' / 'workflows' / 'deploy-pos.yml'


def test_production_equivalent_ci_keeps_required_security_and_runtime_gates():
    text = WORKFLOW.read_text(encoding='utf-8')
    required = [
        'postgres:16',
        'redis:7',
        'alembic upgrade 0008_manager_approval_grants',
        'alembic downgrade 0008_manager_approval_grants',
        'alembic check',
        'app.workers.sync_worker',
        'test_postgres_manager_approval_concurrency.py',
        'test_redis_runtime_integration.py',
        'ci_kds_stream_load.py',
        'KDS_LOAD_STREAMS=20',
        'cache-dependency-path: backend/requirements-dev.lock',
        'pip install -r requirements-dev.lock',
        'npx playwright install',
        'npm run test:e2e',
        'pip-audit -r requirements.lock',
        'npm audit --omit=dev --audit-level=high',
    ]
    missing = [value for value in required if value not in text]
    assert missing == []


def test_browser_e2e_keeps_axe_and_security_workflows():
    text = (ROOT / 'frontend' / 'e2e' / 'production-equivalent.spec.mjs').read_text(encoding='utf-8')
    for required in [
        '@axe-core/playwright',
        "localStorage.getItem('pos_token')",
        '/auth/refresh',
        "name: 'Logout'",
        "width: 390",
        'data-route-status=\"403\"',
        'pass9-route-that-does-not-exist',
        '/customer-display/pairing-code',
        '/customer-display/activate',
        '/revoke',
        "['serious', 'critical']",
    ]:
        assert required in text


def test_deploy_workflow_captures_remote_evidence_before_uploading_it():
    text = DEPLOY_WORKFLOW.read_text(encoding='utf-8')
    assert 'capture_stdout: true' in text
    assert '${{ steps.evidence.outputs.stdout }}' in text
    assert 'test -s "deployment-evidence/${RELEASE_SHA}.txt"' in text
    assert 'appleboy/scp-action@' not in text


def test_workflow_actions_are_pinned_to_immutable_commits():
    action_ref = re.compile(r'^\s*-?\s*uses:\s+[^\s@]+@([^\s#]+)', re.MULTILINE)
    for workflow in (ROOT / '.github' / 'workflows').glob('*.yml'):
        refs = action_ref.findall(workflow.read_text(encoding='utf-8'))
        assert refs, f'{workflow.name} declares no actions'
        assert all(re.fullmatch(r'[0-9a-f]{40}', ref) for ref in refs), workflow.name
