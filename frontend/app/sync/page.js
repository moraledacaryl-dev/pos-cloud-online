'use client';

import { Fragment, useEffect, useMemo, useState } from 'react';
import { fetchOutbox, fetchSyncStatus, runOutboxSync, retryOutboxEvent, unblockOutboxEvent, archiveOutboxEvent, resolveOutboxEvent } from '../../lib/api';
import { humanizeCode } from '../../lib/displayLabels.mjs';
import { explainSyncError, summarizeOutboxRows } from '../../lib/ui_contracts.mjs';
import ActionModal from '../../components/ActionModal';

function formatDateTime(value) {
  if (!value) return '-';
  try { return new Date(value).toLocaleString(); } catch { return String(value); }
}

const STATUS_VIEWS = ['all', 'pending', 'failed', 'blocked', 'suppressed', 'resolved', 'archived', 'synced'];

export default function SyncPage() {
  const [rows, setRows] = useState([]);
  const [health, setHealth] = useState(null);
  const [filters, setFilters] = useState({ status: 'all', q: '', showArchived: false });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [pendingAction, setPendingAction] = useState(null);

  async function loadRows({ silent = false } = {}) {
    if (!silent) setLoading(true);
    setError('');
    try {
      const [data, syncHealth] = await Promise.all([
        fetchOutbox({ limit: 300 }),
        fetchSyncStatus(),
      ]);
      setRows(Array.isArray(data) ? data : []);
      setHealth(syncHealth || null);
    } catch (e) {
      setError(e.message || 'Failed to load sync queue.');
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => { loadRows().catch(console.error); }, []);

  const summary = useMemo(() => summarizeOutboxRows(rows), [rows]);
  const filteredRows = useMemo(() => {
    const q = String(filters.q || '').trim().toLowerCase();
    return rows.filter((row) => {
      if (filters.status !== 'all' && String(row.status || '').toLowerCase() !== filters.status) return false;
      if (!filters.showArchived && String(row.status || '').toLowerCase() === 'synced') return false;
      if (!q) return true;
      return [row.event_type, row.aggregate_type, row.aggregate_id, row.last_error, row.idempotency_key].some((value) => String(value || '').toLowerCase().includes(q));
    });
  }, [rows, filters]);

  const retryRows = useMemo(() => filteredRows.filter((row) => ['failed', 'pending', 'inventory_retry'].includes(String(row.status || '').toLowerCase())), [filteredRows]);

  const queueTitle = filters.status === 'all' ? 'All Queue' : filters.status === 'synced' ? 'Synced' : `${filters.status.charAt(0).toUpperCase() + filters.status.slice(1)}`;

  async function handleRun(limit = 50) {
    setError('');
    setNotice('');
    try {
      const res = await runOutboxSync({ limit });
      setNotice(`Processed ${res.processed}. Synced ${res.synced}, failed ${res.failed}, blocked ${res.blocked}.`);
      await loadRows({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to run sync.');
    }
  }

  async function handleRetry(eventId) {
    setError('');
    setNotice('');
    try {
      const res = await retryOutboxEvent(eventId);
      if (res.ok) {
        setNotice(`Event ${eventId} ${res.synced ? 'synced' : res.failed ? 'failed again' : 'blocked'}.`);
      } else {
        setError(res.error || 'Retry failed.');
      }
      await loadRows({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to retry event.');
    }
  }

  async function handleUnblock(eventId) {
    setError('');
    setNotice('');
    try {
      const res = await unblockOutboxEvent(eventId);
      if (res.ok) {
        setNotice(`Event ${eventId} unblocked.`);
      } else {
        setError(res.error || 'Unblock failed.');
      }
      await loadRows({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to unblock event.');
    }
  }

  async function handleArchive(eventId, reason) {
    setError('');
    setNotice('');
    try {
      const res = await archiveOutboxEvent(eventId, reason);
      if (res.ok) {
        setNotice(`Event ${eventId} archived.`);
      } else {
        setError(res.error || 'Archive failed.');
      }
      await loadRows({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to archive event.');
    }
  }

  async function handleResolve(eventId, resolution) {
    setError('');
    setNotice('');
    try {
      const res = await resolveOutboxEvent(eventId, resolution);
      if (res.ok) {
        setNotice(`Event ${eventId} resolved.`);
      } else {
        setError(res.error || 'Resolve failed.');
      }
      await loadRows({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to resolve event.');
    }
  }

  async function handleRetryAllFailed() {
    setError('');
    setNotice('');
    const failedIds = retryRows.map((row) => row.id);
    if (!failedIds.length) return setError('No retryable events in this view.');
    try {
      let synced = 0, failed = 0, blocked = 0;
      for (const id of failedIds) {
        const res = await retryOutboxEvent(id);
        if (res.ok) {
          if (res.synced) synced++;
          else if (res.failed) failed++;
          else if (res.blocked) blocked++;
        } else {
          failed++;
        }
      }
      setNotice(`Retried ${failedIds.length} events: ${synced} synced, ${failed} failed, ${blocked} blocked.`);
      await loadRows({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to retry all.');
    }
  }

  function toggleExpanded(id) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function confirmPendingAction(value) {
    if (!pendingAction) return;
    if (pendingAction.kind === 'unblock') return handleUnblock(pendingAction.eventId);
    if (pendingAction.kind === 'archive') return handleArchive(pendingAction.eventId, value || 'Manual archive');
    return handleResolve(pendingAction.eventId, value || 'Manually resolved');
  }

  const workerBadge = health?.sync_worker?.is_stale ? 'warn' : 'success';
  const accountingBadge = health?.accounting_api?.ok ? 'success' : 'danger';
  const dbBadge = health?.database?.ok ? 'success' : 'danger';

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Sync Queue</h1>
            <p className="muted">Manager view for outgoing accounting sync health, retry activity, and recovery actions. Use this page only for integration diagnostics and queue repair.</p>
          </div>
          <div className="row wrap">
            <button className="secondary" onClick={() => handleRun(25)}>Run 25</button>
            <button className="primary" onClick={() => handleRun(100)}>Run 100</button>
            <button className="warn" onClick={handleRetryAllFailed} disabled={!retryRows.length}>Retry Retryable ({retryRows.length})</button>
          </div>
        </div>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <div className="card-grid">
          <div className="card"><div className="muted">Pending</div><div className="kpi">{summary.pending}</div><div className="small muted">Ready to send</div></div>
          <div className="card"><div className="muted">Failed</div><div className="kpi">{summary.failed}</div><div className="small muted">Need recovery</div></div>
          <div className="card"><div className="muted">Blocked</div><div className="kpi">{summary.blocked}</div><div className="small muted">Dependency or rule block</div></div>
          <div className="card"><div className="muted">Optional / Suppressed</div><div className="kpi">{summary.suppressed}</div><div className="small muted">No delivery attempted</div></div>
          <div className="card"><div className="muted">Retrying</div><div className="kpi">{summary.retrying}</div><div className="small muted">Already attempted</div></div>
        </div>
      </section>

      <section className="section">
        <div className="toolbar">
          <div>
            <h2>Diagnostics</h2>
            <p className="muted">Surface worker staleness, API reachability, and migration state before forcing retries.</p>
          </div>
          {loading && <span className="badge info">Refreshing…</span>}
        </div>
        <div className="card-grid" style={{ marginTop: 12 }}>
          <div className="card">
            <div className="row wrap"><span className={`badge ${dbBadge}`}>Database</span><span className="small muted">{health?.database?.scheme || '-'}</span></div>
            <div className="small muted" style={{ marginTop: 8 }}>Migration: {health?.database?.migration?.current || health?.database?.migration?.detail || 'Unknown'}</div>
          </div>
          <div className="card">
            <div className="row wrap"><span className={`badge ${accountingBadge}`}>Accounting API</span><span className="small muted">{health?.accounting_api?.configured ? 'Configured' : 'Not configured'}</span></div>
            <div className="small muted" style={{ marginTop: 8 }}>{health?.accounting_api?.url || health?.accounting_api?.error || 'No endpoint configured'}</div>
          </div>
          <div className="card">
            <div className="row wrap"><span className={`badge ${workerBadge}`}>Sync worker</span><span className="small muted">{health?.sync_worker?.age_seconds != null ? `${health.sync_worker.age_seconds}s ago` : 'No heartbeat yet'}</span></div>
            <div className="small muted" style={{ marginTop: 8 }}>Last seen: {formatDateTime(health?.sync_worker?.last_seen_at)}</div>
          </div>
          <div className="card">
            <div className="row wrap"><span className="badge info">Reachability</span><span className="small muted">Ticket store: {health?.integration_reachability?.redis == null ? `${health?.kds_stream_ticket_store?.backend || 'local'} (Redis not required)` : health.integration_reachability.redis ? 'Redis up' : 'Redis down'}</span></div>
            <div className="small muted" style={{ marginTop: 8 }}>Accounting reachable: {health?.integration_reachability?.accounting_api ? 'yes' : 'no'}</div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="toolbar">
          <div>
            <h2>Recovery Queue</h2>
            <p className="muted">Filter the outbox by status, then focus on rows with errors or retries before reopening archived synced items.</p>
          </div>
        </div>

        <div className="form-grid sync-filter-grid" style={{ marginTop: 12 }}>
          <label className="field">
            Search
            <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder="event type, aggregate, idempotency key, error" />
          </label>
          <label className="field">
            Queue View
            <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))}>
              {STATUS_VIEWS.map((status) => <option key={status} value={status}>{humanizeCode(status)}</option>)}
            </select>
          </label>
          <label className="field-inline" style={{ alignSelf: 'end' }}>
            <input type="checkbox" checked={filters.showArchived} onChange={(e) => setFilters((prev) => ({ ...prev, showArchived: e.target.checked }))} />
            Include archived synced rows
          </label>
        </div>

        <div className="card" style={{ marginTop: 14 }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <strong>{queueTitle}</strong>
            <span className="small muted">{filteredRows.length} rows</span>
          </div>
          <table className="table sync-desktop-table" tabIndex={0} aria-label="Scrollable data table" style={{ marginTop: 10 }}>
            <thead><tr><th>ID</th><th>Type</th><th>Aggregate</th><th>Status</th><th>Retries</th><th>Last attempt</th><th>Error</th><th>Details</th><th>Actions</th></tr></thead>
            <tbody>
              {filteredRows.map((row) => {
                const explanation = explainSyncError(row);
                return (
                <Fragment key={row.id}>
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td>{humanizeCode(row.event_type, 'Sync Event')}</td>
                    <td>{humanizeCode(row.aggregate_type, 'Record')} #{row.aggregate_id}</td>
                    <td><span className={`badge ${row.status === 'failed' ? 'danger' : row.status === 'blocked' ? 'warn' : row.status === 'suppressed' ? 'muted' : row.status === 'resolved' ? 'success' : 'info'}`}>{humanizeCode(row.status)}</span></td>
                    <td>{row.retry_count}</td>
                    <td>{formatDateTime(row.last_attempt_at || row.next_retry_at)}</td>
                    <td><div className="small muted">{row.last_error ? explanation.summary : '-'}</div></td>
                    <td><button type="button" className="small secondary" onClick={() => toggleExpanded(row.id)}>{expandedRows.has(row.id) ? 'Hide' : 'Show'}</button></td>
                    <td>
                      <div className="row wrap" style={{ gap: 4 }}>
                        {['failed', 'pending', 'inventory_retry'].includes(String(row.status || '').toLowerCase()) && (
                          <button type="button" className="small secondary" onClick={() => handleRetry(row.id)}>Retry now</button>
                        )}
                        {String(row.status || '').toLowerCase() === 'blocked' && (
                          <button type="button" className="small warn" onClick={() => setPendingAction({ kind: 'unblock', eventId: row.id })}>Unblock</button>
                        )}
                        {['failed', 'blocked'].includes(String(row.status || '').toLowerCase()) && (
                          <button type="button" className="small danger" onClick={() => setPendingAction({ kind: 'archive', eventId: row.id })}>Archive</button>
                        )}
                        {['failed', 'blocked'].includes(String(row.status || '').toLowerCase()) && (
                          <button type="button" className="small success" onClick={() => setPendingAction({ kind: 'resolve', eventId: row.id })}>Resolve</button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedRows.has(row.id) && (
                    <tr key={`details-${row.id}`}>
                      <td colSpan="9" style={{ padding: '8px 16px', background: 'var(--color-bg-secondary)' }}>
                        <div className="stack-tight">
                          <div><strong>What this event is:</strong> {humanizeCode(row.event_type, 'Sync Event')} for {humanizeCode(row.aggregate_type, 'Record')} #{row.aggregate_id}</div>
                          <div><strong>Why it failed:</strong> {explanation.summary}</div>
                          <div><strong>Recommended action:</strong> {explanation.action}</div>
                          <div><strong>Raw Error:</strong> {row.last_error || 'None'}</div>
                          <div><strong>Idempotency Key:</strong> {row.idempotency_key || 'None'}</div>
                          <div><strong>Payload:</strong> <pre style={{ fontSize: 10, margin: 0 }}>{JSON.stringify(row.payload || {}, null, 2)}</pre></div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );})}
              {!filteredRows.length && <tr><td colSpan="9" className="muted">No rows in the current view.</td></tr>}
            </tbody>
          </table>
          <div className="sync-mobile-list" aria-label="Sync queue mobile summary">
            {filteredRows.map((row) => {
              const explanation = explainSyncError(row);
              return <article className="sync-mobile-card" key={`mobile-${row.id}`}>
                <div className="sync-mobile-identity"><strong>Event #{row.id}</strong><span className={`badge ${row.status === 'failed' ? 'danger' : row.status === 'blocked' ? 'warn' : row.status === 'suppressed' ? 'muted' : row.status === 'resolved' ? 'success' : 'info'}`}>{humanizeCode(row.status)}</span></div>
                <div><strong>{humanizeCode(row.event_type, 'Sync Event')}</strong><div className="small muted">{humanizeCode(row.aggregate_type, 'Record')} #{row.aggregate_id}</div></div>
                <div className="small"><strong>Last attempt:</strong> {formatDateTime(row.last_attempt_at || row.next_retry_at)}</div>
                <div className="small"><strong>Summary:</strong> {row.last_error ? explanation.summary : 'No error recorded.'}</div>
                <details className="technical-details"><summary>Technical details</summary><div className="stack-tight"><div><strong>Recommended action:</strong> {explanation.action}</div><div><strong>Raw error:</strong> {row.last_error || 'None'}</div><div><strong>Idempotency key:</strong> {row.idempotency_key || 'None'}</div><pre>{JSON.stringify(row.payload || {}, null, 2)}</pre></div></details>
                <div className="row wrap">
                  {['failed', 'pending', 'inventory_retry'].includes(String(row.status || '').toLowerCase()) && <button type="button" className="secondary" onClick={() => handleRetry(row.id)}>Retry now</button>}
                  {String(row.status || '').toLowerCase() === 'blocked' && <button type="button" className="warn" onClick={() => setPendingAction({ kind: 'unblock', eventId: row.id })}>Unblock</button>}
                  {['failed', 'blocked'].includes(String(row.status || '').toLowerCase()) && <button type="button" className="danger" onClick={() => setPendingAction({ kind: 'archive', eventId: row.id })}>Archive</button>}
                  {['failed', 'blocked'].includes(String(row.status || '').toLowerCase()) && <button type="button" className="success" onClick={() => setPendingAction({ kind: 'resolve', eventId: row.id })}>Resolve</button>}
                </div>
              </article>;
            })}
            {!filteredRows.length && <p className="muted">No rows in the current view.</p>}
          </div>
        </div>
      </section>
      <ActionModal
        open={!!pendingAction}
        title={pendingAction?.kind === 'unblock' ? `Unblock event ${pendingAction?.eventId}?` : pendingAction?.kind === 'archive' ? `Archive event ${pendingAction?.eventId}?` : `Resolve event ${pendingAction?.eventId}?`}
        description={pendingAction?.kind === 'unblock' ? 'The event will return to pending and become eligible for retry.' : 'Record a short note so the recovery decision remains clear later.'}
        fieldLabel={pendingAction?.kind === 'resolve' ? 'Resolution note' : 'Reason'}
        defaultValue={pendingAction?.kind === 'archive' ? 'Manual archive' : pendingAction?.kind === 'resolve' ? 'Manually resolved' : ''}
        required={pendingAction?.kind !== 'unblock'}
        confirmLabel={pendingAction?.kind === 'unblock' ? 'Unblock event' : pendingAction?.kind === 'archive' ? 'Archive event' : 'Resolve event'}
        tone={pendingAction?.kind === 'resolve' ? 'normal' : 'danger'}
        onClose={() => setPendingAction(null)}
        onConfirm={confirmPendingAction}
      />
    </div>
  );
}
