from __future__ import annotations


def evaluate_operational_readiness(
    *,
    database_ok: bool,
    migrations_ok: bool,
    security_ok: bool,
    worker_stale: bool,
    failed_events: int = 0,
    blocked_events: int = 0,
    accounting_configured: bool = False,
    accounting_reachable: bool = True,
) -> dict:
    """Separate core POS sales readiness from downstream integration health.

    A temporary Accounting/Inventory integration outage must not stop cashiers
    from selling, but it must be visible as degraded health to operations and
    monitoring. Core readiness therefore covers database/schema/security only,
    while integration readiness covers the worker and unresolved outbox state.
    """

    core_reasons: list[str] = []
    integration_reasons: list[str] = []

    if not database_ok:
        core_reasons.append('database_unavailable')
    if not migrations_ok:
        core_reasons.append('database_migration_required')
    if not security_ok:
        core_reasons.append('security_configuration_invalid')

    if worker_stale:
        integration_reasons.append('sync_worker_stale')
    if int(failed_events or 0) > 0:
        integration_reasons.append('outbox_failed_events')
    if int(blocked_events or 0) > 0:
        integration_reasons.append('outbox_blocked_events')
    if accounting_configured and not accounting_reachable:
        integration_reasons.append('accounting_unreachable')

    sales_ready = not core_reasons
    integrations_ready = not integration_reasons
    fully_healthy = sales_ready and integrations_ready

    if not sales_ready:
        status = 'unready'
    elif not integrations_ready:
        status = 'degraded'
    else:
        status = 'healthy'

    return {
        'ok': fully_healthy,
        'status': status,
        'sales_ready': sales_ready,
        'integrations_ready': integrations_ready,
        'reasons': core_reasons + integration_reasons,
        'core_reasons': core_reasons,
        'integration_reasons': integration_reasons,
    }
