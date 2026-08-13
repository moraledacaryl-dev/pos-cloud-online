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
    kds_ticket_store_required: bool = False,
    kds_ticket_store_reachable: bool = True,
) -> dict:
    """Separate core POS sales readiness from downstream/operational dependencies.

    A temporary Accounting/Inventory/KDS realtime dependency outage must not stop
    cashiers from recording local sales, but it must be visible as degraded health
    to operations and monitoring. Core readiness therefore covers database/schema/
    security, while integration readiness covers worker/outbox/downstream and KDS
    realtime dependencies.
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
    if kds_ticket_store_required and not kds_ticket_store_reachable:
        integration_reasons.append('kds_ticket_store_unavailable')

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
