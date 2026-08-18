'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { approveApproval, fetchApprovals, fetchAuditLogs, rejectApproval } from '../../lib/api';

const EMPTY_FILTERS = {
  q: '', action: '', entity_type: '', actor_user_id: '', date_from: '', date_to: '',
  approval_status: '', approval_type: '', limit: 50,
};

function formatDateTime(value) {
  if (!value) return '-';
  try { return new Date(value).toLocaleString(); } catch { return String(value); }
}

export default function AuditPage() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [rows, setRows] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [cursorHistory, setCursorHistory] = useState([]);
  const [currentCursor, setCurrentCursor] = useState(null);
  const [selectedAuditId, setSelectedAuditId] = useState(null);
  const [selectedApprovalId, setSelectedApprovalId] = useState(null);
  const [decisionNote, setDecisionNote] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  async function loadAll(nextFilters = filters, beforeId = null, resetHistory = false) {
    setLoading(true);
    setError('');
    try {
      const auditParams = { ...nextFilters, before_id: beforeId || undefined };
      if (!auditParams.actor_user_id) delete auditParams.actor_user_id;
      delete auditParams.approval_status;
      delete auditParams.approval_type;
      const approvalParams = {
        limit: 50,
        q: nextFilters.q || undefined,
        status: nextFilters.approval_status || undefined,
        approval_type: nextFilters.approval_type || undefined,
        entity_type: nextFilters.entity_type || undefined,
        date_from: nextFilters.date_from || undefined,
        date_to: nextFilters.date_to || undefined,
      };
      const [auditPage, approvalRows] = await Promise.all([
        fetchAuditLogs(auditParams),
        fetchApprovals(approvalParams),
      ]);
      const nextAuditRows = Array.isArray(auditPage?.items) ? auditPage.items : [];
      const nextApprovalRows = Array.isArray(approvalRows) ? approvalRows : [];
      setRows(nextAuditRows);
      setApprovals(nextApprovalRows);
      setNextCursor(auditPage?.next_cursor || null);
      setCurrentCursor(beforeId || null);
      if (resetHistory) setCursorHistory([]);
      setSelectedAuditId(nextAuditRows[0]?.id || null);
      setSelectedApprovalId(nextApprovalRows[0]?.id || null);
      setNotice(`Loaded ${nextAuditRows.length} audit rows on this page and ${nextApprovalRows.length} approvals.`);
    } catch (e) {
      setError(e.message || 'Failed to load audit logs.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll(EMPTY_FILTERS, null, true).catch(console.error); }, []);

  async function goNext() {
    if (!nextCursor || loading) return;
    setCursorHistory((history) => [...history, currentCursor]);
    await loadAll(filters, nextCursor, false);
  }

  async function goPrevious() {
    if (!cursorHistory.length || loading) return;
    const previous = cursorHistory[cursorHistory.length - 1];
    setCursorHistory((history) => history.slice(0, -1));
    await loadAll(filters, previous, false);
  }

  async function handleApprove() {
    if (!selectedApproval) return;
    try {
      await approveApproval(selectedApproval.id, { decision_note: decisionNote || null });
      setDecisionNote('');
      await loadAll(filters, currentCursor, false);
      setNotice('Approval approved successfully.');
    } catch (e) { setError(e.message || 'Failed to approve.'); }
  }

  async function handleReject() {
    if (!selectedApproval) return;
    try {
      await rejectApproval(selectedApproval.id, { decision_note: decisionNote || null });
      setDecisionNote('');
      await loadAll(filters, currentCursor, false);
      setNotice('Approval rejected successfully.');
    } catch (e) { setError(e.message || 'Failed to reject.'); }
  }

  const selectedAudit = useMemo(() => rows.find((row) => row.id === selectedAuditId) || rows[0] || null, [rows, selectedAuditId]);
  const selectedApproval = useMemo(() => approvals.find((row) => row.id === selectedApprovalId) || approvals[0] || null, [approvals, selectedApprovalId]);
  const exceptions = useMemo(() => rows.filter((row) => Number(row.status_code || 200) >= 400 || /void|refund|write_off|reopen|dispute/i.test(String(row.action || ''))).length, [rows]);

  function setField(key, value) { setFilters((prev) => ({ ...prev, [key]: value })); }
  function renderLinks(row) {
    const entries = Object.entries(row?.links || {});
    if (!entries.length) return <span className="muted">-</span>;
    return <div className="row wrap">{entries.map(([key, href]) => <Link key={key} href={href} className="secondary-link">{key}</Link>)}</div>;
  }

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div><h1>Audit Log</h1><p className="muted">Business and security events only. Routine request traffic remains in structured access logs.</p></div>
          {loading && <span className="badge info">Loading…</span>}
        </div>
        {!!notice && <p className="notice-text">{notice}</p>}
        {!!error && <p className="error-text">{error}</p>}
      </section>

      <section className="section">
        <div className="card-grid" style={{ marginBottom: 14 }}>
          <div className="card"><div className="muted">Rows on page</div><div className="kpi">{rows.length}</div></div>
          <div className="card"><div className="muted">Potential exceptions</div><div className="kpi">{exceptions}</div></div>
          <div className="card"><div className="muted">Pending approvals</div><div className="kpi">{approvals.filter((row) => row.status === 'pending').length}</div></div>
        </div>
        <form className="form-grid audit-filter-grid" onSubmit={(e) => { e.preventDefault(); loadAll(filters, null, true).catch(console.error); }}>
          <label className="field">Search<input value={filters.q} onChange={(e) => setField('q', e.target.value)} /></label>
          <label className="field">Action<input value={filters.action} onChange={(e) => setField('action', e.target.value)} /></label>
          <label className="field">Entity<input value={filters.entity_type} onChange={(e) => setField('entity_type', e.target.value)} /></label>
          <label className="field">Actor User ID<input value={filters.actor_user_id} onChange={(e) => setField('actor_user_id', e.target.value)} /></label>
          <label className="field">Approval Status<select value={filters.approval_status} onChange={(e) => setField('approval_status', e.target.value)}><option value="">All</option><option value="pending">pending</option><option value="approved">approved</option><option value="rejected">rejected</option></select></label>
          <label className="field">Approval Type<input value={filters.approval_type} onChange={(e) => setField('approval_type', e.target.value)} /></label>
          <label className="field">Date From<input type="date" value={filters.date_from} onChange={(e) => setField('date_from', e.target.value)} /></label>
          <label className="field">Date To<input type="date" value={filters.date_to} onChange={(e) => setField('date_to', e.target.value)} /></label>
          <label className="field">Page Size<select value={filters.limit} onChange={(e) => setField('limit', Number(e.target.value))}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label>
          <div className="row wrap" style={{ gridColumn: '1 / -1' }}>
            <button type="submit" className="primary">Apply Filters</button>
            <button type="button" className="secondary" onClick={() => { setFilters(EMPTY_FILTERS); loadAll(EMPTY_FILTERS, null, true).catch(console.error); }}>Reset</button>
          </div>
        </form>
      </section>

      <section className="section">
        <div className="two-column-layout audit-review-layout">
          <div className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}><strong>Approvals review queue</strong><span className="small muted">{approvals.length} rows</span></div>
            <div className="stack-tight" style={{ marginTop: 10 }}>
              {approvals.map((row) => <button key={row.id} type="button" className={`list-row-button ${selectedApproval?.id === row.id ? 'active' : ''}`} onClick={() => setSelectedApprovalId(row.id)}><div><strong>{row.approval_type}</strong><div className="small muted">{row.status} · {row.entity_type} #{row.entity_id || '-'}</div></div></button>)}
              {!approvals.length && <div className="muted">No approvals found.</div>}
            </div>
          </div>
          <div className="card">
            {!selectedApproval && <div className="muted">Select an approval.</div>}
            {!!selectedApproval && <div className="stack-tight">
              <div><strong>{selectedApproval.approval_type}</strong><div className="small muted">{selectedApproval.status} · {selectedApproval.entity_type} #{selectedApproval.entity_id || '-'}</div></div>
              <div className="card"><div className="muted">Requested by</div><strong>{selectedApproval.requested_by_name || '-'}</strong></div>
              <div className="card"><div className="muted">Approved by</div><strong>{selectedApproval.approved_by_name || '-'}</strong></div>
              <div className="card"><div className="muted">Reason</div>{selectedApproval.requested_reason || '-'}</div>
              {selectedApproval.status === 'pending' && <div className="stack-tight"><textarea value={decisionNote} onChange={(e) => setDecisionNote(e.target.value)} placeholder="Decision note" /><div className="row wrap"><button type="button" className="primary" onClick={handleApprove}>Approve</button><button type="button" className="danger" onClick={handleReject}>Reject</button></div></div>}
            </div>}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="toolbar" style={{ marginBottom: 10 }}>
          <strong>Audit entries</strong>
          <div className="row wrap">
            <button type="button" className="secondary" onClick={goPrevious} disabled={!cursorHistory.length || loading}>Previous</button>
            <button type="button" className="secondary" onClick={goNext} disabled={!nextCursor || loading}>Next</button>
          </div>
        </div>
        <div className="two-column-layout audit-review-layout">
          <div className="card">
            <div className="stack-tight">
              {rows.map((row) => <button key={row.id} type="button" className={`list-row-button ${selectedAudit?.id === row.id ? 'active' : ''}`} onClick={() => setSelectedAuditId(row.id)}><div><strong>{row.action}</strong><div className="small muted">{formatDateTime(row.created_at)} · {row.actor_name || row.actor_username || '-'}</div><div className="small muted">{row.entity_type} #{row.entity_id || '-'}</div></div></button>)}
              {!rows.length && <div className="muted">No audit rows found.</div>}
            </div>
          </div>
          <div className="card">
            {!selectedAudit && <div className="muted">Select an audit entry.</div>}
            {!!selectedAudit && <div className="stack-tight">
              <div><strong>{selectedAudit.action}</strong><div className="small muted">{selectedAudit.entity_type} #{selectedAudit.entity_id || '-'}</div></div>
              <div className="form-grid-3"><div className="card"><div className="muted">Actor</div><strong>{selectedAudit.actor_name || selectedAudit.actor_username || '-'}</strong></div><div className="card"><div className="muted">Time</div><strong>{formatDateTime(selectedAudit.created_at)}</strong></div><div className="card"><div className="muted">Method</div><strong>{selectedAudit.request_method || '-'}</strong></div></div>
              <div className="card"><div className="muted">Linked records</div>{renderLinks(selectedAudit)}</div>
              <div className="card"><div className="muted">Details JSON</div><pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 12 }}>{JSON.stringify(selectedAudit.details || {}, null, 2)}</pre></div>
            </div>}
          </div>
        </div>
      </section>
    </div>
  );
}
