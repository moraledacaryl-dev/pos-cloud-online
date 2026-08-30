from pathlib import Path

from app.services.reliability_policy import evaluate_operational_readiness


ROOT = Path(__file__).resolve().parents[2]
OPS_SERVICE = ROOT / 'backend' / 'app' / 'services' / 'ops_service.py'


def test_accounting_http_failure_degrades_integration_readiness():
    readiness = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=True,
        worker_stale=False,
        accounting_configured=True,
        accounting_reachable=False,
    )

    assert readiness['sales_ready'] is True
    assert readiness['integrations_ready'] is False
    assert readiness['ok'] is False
    assert readiness['status'] == 'degraded'
    assert 'accounting_unreachable' in readiness['reasons']


def test_ops_service_wires_accounting_health_not_network_reachability():
    text = OPS_SERVICE.read_text()
    assert "accounting_reachable=bool(accounting_api.get('ok', False))" in text
    assert "accounting_reachable=bool(accounting_api.get('reachable', False))" not in text
