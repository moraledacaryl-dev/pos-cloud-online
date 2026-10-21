"""Keep the visual baseline synthetic, healthy and incapable of financial writes."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_accounting_stub_only_serves_health_and_rejects_financial_writes():
    script = (ROOT / "backend/scripts/visual_audit_accounting_stub.py").read_text()
    assert '("127.0.0.1", 18993)' in script
    assert 'VISUAL_AUDIT_CI' in script
    assert 'GITHUB_ACTIONS' in script
    assert '"/pos_visual_audit"' in script
    assert '"/healthz"' in script
    assert 'self.send_error(404' in script
    assert script.count('self.send_error(405') >= 3
    assert 'do_POST' in script and 'do_PUT' in script and 'do_DELETE' in script


def test_visual_health_stub_refuses_execution_outside_disposable_ci():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "backend/scripts/visual_audit_accounting_stub.py")],
        cwd=ROOT,
        env={**os.environ, 'GITHUB_ACTIONS': 'false',
             'VISUAL_AUDIT_CI': '1', 'ENVIRONMENT': 'development',
             'DATABASE_URL': 'postgresql+psycopg://pos:pos@127.0.0.1:5432/pos_visual_audit'},
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert proc.returncode != 0
    assert 'restricted to disposable visual CI' in proc.stderr


def test_visual_workflow_has_real_health_worker_and_emulates_no_production_financial_endpoint():
    content = (ROOT / ".github/workflows/visual-audit-screenshots.yml").read_text()
    assert 'pos_visual_audit' in content and 'postgres:16' in content and 'redis:7' in content
    assert 'ACCOUNTING_API_BASE: http://127.0.0.1:18993/api' in content
    assert 'python -m app.workers.sync_worker' in content
    assert 'python scripts/visual_audit_accounting_stub.py' in content
    assert 'VISUAL_AUDIT_HEALTHY_BASELINE=PASS' in content
    assert 'http://127.0.0.1:8100/readyz/integrations' in content
    assert 'http://127.0.0.1:18993/api/integrations/pos/order' in content
    assert '" = 405' in content or ' = 405' in content
    assert "abort('failed')" in (ROOT / "frontend/e2e/visual-audit.spec.mjs").read_text()
