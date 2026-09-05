from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'production-certify.sh'


def test_production_certification_script_exists_and_is_bash():
    text = SCRIPT.read_text()
    assert text.startswith('#!/usr/bin/env bash')
    assert 'set -euo pipefail' in text


def test_production_certification_is_non_destructive():
    text = SCRIPT.read_text().lower()
    forbidden = [
        'curl -x post',
        'curl --request post',
        'curl -x put',
        'curl --request put',
        'curl -x patch',
        'curl --request patch',
        'curl -x delete',
        'curl --request delete',
        '/api/orders',
        '/api/cash-movements',
        '/api/room-charges',
        '/api/sessions/open',
    ]
    for needle in forbidden:
        assert needle not in text


def test_production_certification_checks_required_health_surfaces():
    text = SCRIPT.read_text()
    for endpoint in (
        '/healthz',
        '/healthz/details',
        '/readyz',
        '/readyz/integrations',
    ):
        assert endpoint in text

    for service in ('pos-backend', 'pos-frontend', 'pos-sync-worker'):
        assert service in text

    for signal in (
        'sales_ready',
        'integrations_ready',
        'is_stale',
        'attention_required',
        'Accounting API is not reachable',
    ):
        assert signal in text


def test_accounting_outage_override_is_explicit_and_narrow():
    text = SCRIPT.read_text()
    assert 'ALLOW_ACCOUNTING_UNAVAILABLE' in text
    assert '{"accounting_unreachable", "outbox_failed_events", "outbox_blocked_events"}' in text
    assert 'allow_accounting_unavailable and accounting_is_unreachable' in text
    assert 'disallowed_integration_reasons' in text
    assert 'value is False' in text
    assert 'key == "accounting_api"' in text


def test_predeploy_checks_core_and_postdeploy_checks_integrations():
    text = SCRIPT.read_text()
    assert 'CERTIFICATION_PHASE' in text
    assert 'predeploy' in text
    assert 'postdeploy' in text
    assert 'integration readiness is evaluated after the candidate starts' in text
