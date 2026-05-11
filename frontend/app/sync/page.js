'use client';

import { useEffect, useMemo, useState } from 'react';
import { fetchOutbox, fetchSyncStatus, runOutboxSync, retryOutboxEvent, unblockOutboxEvent, archiveOutboxEvent, resolveOutboxEvent } from '../../lib/api';
import { summarizeOutboxRows } from '../../lib/ui_contracts.mjs';

function formatDateTime(value) {
  if (!value) return '-';
  try { return new Date(value).toLocaleString(); } catch { return String(value); }
}

const STATUS_VIEWS = ['all', 'pending', 'failed', 'blocked', 'resolved', 'archived', 'synced'];

export default function SyncPage() {
  const [rows, setRows] = useState([]);
  const [health, setHealth] = useState(null);
  const [filters, setFilters] = useState({ status: 'all', q: '', showArchived: false });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [expandedRows, setExpandedRows] = useState(new Set());

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

  const retryRows = useMemo(() => filteredRows.filter((row) => ['failed', 'blocked', 'pending'].includes(String(row.status || '').toLowerCase())), [filteredRows]);

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
    if (!confirm('Unblock this event? It will be marked as pending for retry.')) return;
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

  async function handleArchive(eventId) {
    const reason = prompt('Reason for archiving (optional):', 'Manual archive');
    if (reason === null) return; // cancelled
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

  async function handleResolve(eventId) {
    const resolution = prompt('Resolution note (optional):', 'Manually resolved');
    if (resolution === null) return; // cancelled
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
    if (!failedIds.length) return setError('No failed events to retry.');
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
            <button className="warn" onClick={handleRetryAllFailed} disabled={!retryRows.length}>Retry All Failed ({retryRows.length})</button>
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
            <div className="row wrap"><span className="badge info">Reachability</span><span className="small muted">Redis: {health?.integration_reachability?.redis ? 'up' : 'down'}</span></div>
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
              {STATUS_VIEWS.map((status) => <option key={status} value={status}>{status}</option>)}
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
          <table className="table" style={{ marginTop: 10 }}>
            <thead><tr><th>ID</th><th>Type</th><th>Aggregate</th><th>Status</th><th>Retries</th><th>Last attempt</th><th>Error</th><th>Details</th><th>Actions</th></tr></thead>
            <tbody>
              {filteredRows.map((row) => (
                <>
                  <tr key={row.id}>
                    <td>{row.id}</td>
                    <td>{row.event_type}</td>
                    <td>{row.aggregate_type} #{row.aggregate_id}</td>
                    <td><span className={`badge ${row.status === 'failed' ? 'danger' : row.status === 'blocked' ? 'warn' : row.status === 'resolved' ? 'success' : row.status === 'archived' ? 'info' : 'info'}`}>{row.status}</span></td>
                    <td>{row.retry_count}</td>
                    <td>{formatDateTime(row.last_attempt_at || row.next_retry_at)}</td>
                    <td><div className="small muted">{row.last_error ? row.last_error.substring(0, 50) + (row.last_error.length > 50 ? '...' : '') : '-'}</div></td>
                    <td><button type="button" className="small secondary" onClick={() => toggleExpanded(row.id)}>{expandedRows.has(row.id) ? 'Hide' : 'Show'}</button></td>
                    <td>
                      <div className="row wrap" style={{ gap: 4 }}>
                        {['failed', 'blocked', 'pending'].includes(String(row.status || '').toLowerCase()) && (
                          <button type="button" className="small secondary" onClick={() => handleRetry(row.id)}>Retry</button>
                        )}
                        {String(row.status || '').toLowerCase() === 'blocked' && (
                          <button type="button" className="small warn" onClick={() => handleUnblock(row.id)}>Unblock</button>
                        )}
                        {['failed', 'blocked'].includes(String(row.status || '').toLowerCase()) && (
                          <button type="button" className="small danger" onClick={() => handleArchive(row.id)}>Archive</button>
                        )}
                        {['failed', 'blocked'].includes(String(row.status || '').toLowerCase()) && (
                          <button type="button" className="small success" onClick={() => handleResolve(row.id)}>Resolve</button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedRows.has(row.id) && (
                    <tr key={`details-${row.id}`}>
                      <td colSpan="9" style={{ padding: '8px 16px', background: 'var(--color-bg-secondary)' }}>
                        <div className="stack-tight">
                          <div><strong>Full Error:</strong> {row.last_error || 'None'}</div>
                          <div><strong>Idempotency Key:</strong> {row.idempotency_key || 'None'}</div>
                          <div><strong>Payload:</strong> <pre style={{ fontSize: 10, margin: 0 }}>{JSON.stringify(row.payload || {}, null, 2)}</pre></div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
              {!filteredRows.length && <tr><td colSpan="9" className="muted">No rows in the current view.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
