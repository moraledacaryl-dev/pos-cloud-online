from app.services.reliability_policy import evaluate_operational_readiness


def test_fully_healthy_when_core_and_integrations_are_clean():
    result = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=True,
        worker_stale=False,
        failed_events=0,
        blocked_events=0,
        accounting_configured=True,
        accounting_reachable=True,
    )
    assert result['ok'] is True
    assert result['sales_ready'] is True
    assert result['integrations_ready'] is True
    assert result['status'] == 'healthy'
    assert result['reasons'] == []


def test_stale_worker_degrades_integrations_without_stopping_sales():
    result = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=True,
        worker_stale=True,
    )
    assert result['ok'] is False
    assert result['sales_ready'] is True
    assert result['integrations_ready'] is False
    assert result['status'] == 'degraded'
    assert 'sync_worker_stale' in result['reasons']


def test_failed_outbox_event_is_visible_as_degraded_health():
    result = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=True,
        worker_stale=False,
        failed_events=1,
    )
    assert result['ok'] is False
    assert result['sales_ready'] is True
    assert 'outbox_failed_events' in result['integration_reasons']


def test_blocked_outbox_event_is_visible_as_degraded_health():
    result = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=True,
        worker_stale=False,
        blocked_events=2,
    )
    assert result['ok'] is False
    assert result['sales_ready'] is True
    assert 'outbox_blocked_events' in result['integration_reasons']


def test_accounting_outage_is_degraded_not_core_unready():
    result = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=True,
        worker_stale=False,
        accounting_configured=True,
        accounting_reachable=False,
    )
    assert result['ok'] is False
    assert result['sales_ready'] is True
    assert result['status'] == 'degraded'
    assert 'accounting_unreachable' in result['reasons']


def test_unconfigured_accounting_does_not_create_reachability_reason():
    result = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=True,
        worker_stale=False,
        accounting_configured=False,
        accounting_reachable=False,
    )
    assert 'accounting_unreachable' not in result['reasons']


def test_required_kds_ticket_store_outage_degrades_integrations_not_sales():
    result = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=True,
        worker_stale=False,
        kds_ticket_store_required=True,
        kds_ticket_store_reachable=False,
    )
    assert result['ok'] is False
    assert result['sales_ready'] is True
    assert result['integrations_ready'] is False
    assert result['status'] == 'degraded'
    assert 'kds_ticket_store_unavailable' in result['integration_reasons']


def test_optional_memory_kds_store_does_not_claim_redis_dependency():
    result = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=True,
        worker_stale=False,
        kds_ticket_store_required=False,
        kds_ticket_store_reachable=False,
    )
    assert 'kds_ticket_store_unavailable' not in result['reasons']


def test_database_or_migration_failure_makes_sales_unready():
    database_failure = evaluate_operational_readiness(
        database_ok=False,
        migrations_ok=True,
        security_ok=True,
        worker_stale=False,
    )
    assert database_failure['sales_ready'] is False
    assert database_failure['status'] == 'unready'
    assert 'database_unavailable' in database_failure['core_reasons']

    migration_failure = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=False,
        security_ok=True,
        worker_stale=False,
    )
    assert migration_failure['sales_ready'] is False
    assert 'database_migration_required' in migration_failure['core_reasons']


def test_security_failure_makes_sales_unready():
    result = evaluate_operational_readiness(
        database_ok=True,
        migrations_ok=True,
        security_ok=False,
        worker_stale=False,
    )
    assert result['ok'] is False
    assert result['sales_ready'] is False
    assert result['status'] == 'unready'
    assert 'security_configuration_invalid' in result['core_reasons']
