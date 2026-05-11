'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { fetchApprovals, fetchAuditLogs, approveApproval, rejectApproval } from '../../lib/api';

function formatDateTime(value) {
  if (!value) return '-';
  try { return new Date(value).toLocaleString(); } catch { return String(value); }
}

export default function AuditPage() {
  const [filters, setFilters] = useState({ q: '', action: '', entity_type: '', actor_user_id: '', date_from: '', date_to: '', approval_status: '', approval_type: '', limit: 200 });
  const [rows, setRows] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [selectedAuditId, setSelectedAuditId] = useState(null);
  const [selectedApprovalId, setSelectedApprovalId] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [decisionNote, setDecisionNote] = useState('');
  const [loading, setLoading] = useState(true);

  async function loadAll(nextFilters = filters) {
    setLoading(true);
    setError('');
    try {
      const auditParams = { ...nextFilters };
      if (!auditParams.actor_user_id) delete auditParams.actor_user_id;
      delete auditParams.approval_status;
      delete auditParams.approval_type;
      const approvalParams = {
        limit: 100,
        q: nextFilters.q || undefined,
        status: nextFilters.approval_status || undefined,
        approval_type: nextFilters.approval_type || undefined,
        entity_type: nextFilters.entity_type || undefined,
        date_from: nextFilters.date_from || undefined,
        date_to: nextFilters.date_to || undefined,
      };
      const [auditRows, approvalRows] = await Promise.all([
        fetchAuditLogs(auditParams),
        fetchApprovals(approvalParams),
      ]);
      const nextAuditRows = Array.isArray(auditRows) ? auditRows : [];
      const nextApprovalRows = Array.isArray(approvalRows) ? approvalRows : [];
      setRows(nextAuditRows);
      setApprovals(nextApprovalRows);
      setSelectedAuditId(nextAuditRows[0]?.id || null);
      setSelectedApprovalId(nextApprovalRows[0]?.id || null);
      setNotice(`Loaded ${nextAuditRows.length} audit rows and ${nextApprovalRows.length} approvals.`);
    } catch (e) {
      setError(e.message || 'Failed to load audit logs.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll().catch(console.error); }, []);

  async function handleApprove() {
    if (!selectedApproval) return;
    setError('');
    try {
      await approveApproval(selectedApproval.id, { decision_note: decisionNote || null });
      setNotice('Approval approved successfully.');
      setDecisionNote('');
      await loadAll();
    } catch (e) {
      setError(e.message || 'Failed to approve.');
    }
  }

  async function handleReject() {
    if (!selectedApproval) return;
    setError('');
    try {
      await rejectApproval(selectedApproval.id, { decision_note: decisionNote || null });
      setNotice('Approval rejected successfully.');
      setDecisionNote('');
      await loadAll();
    } catch (e) {
      setError(e.message || 'Failed to reject.');
    }
  }

  const selectedAudit = useMemo(() => rows.find((row) => row.id === selectedAuditId) || rows[0] || null, [rows, selectedAuditId]);
  const selectedApproval = useMemo(() => approvals.find((row) => row.id === selectedApprovalId) || approvals[0] || null, [approvals, selectedApprovalId]);
  const auditSummary = useMemo(() => ({
    loaded: rows.length,
    roomCharges: rows.filter((row) => String(row.entity_type || '').includes('room_charge')).length,
    sessions: rows.filter((row) => String(row.entity_type || '').includes('session')).length,
    exceptions: rows.filter((row) => Number(row.status_code || 200) >= 400 || /void|refund|write_off|reopen|dispute/i.test(String(row.action || ''))).length,
  }), [rows]);
  const approvalSummary = useMemo(() => ({
    pending: approvals.filter((row) => row.status === 'pending').length,
    approved: approvals.filter((row) => row.status === 'approved').length,
  }), [approvals]);

  const activeFilters = useMemo(() => {
    const active = [];
    if (filters.q) active.push(`Search: ${filters.q}`);
    if (filters.action) active.push(`Action: ${filters.action}`);
    if (filters.entity_type) active.push(`Entity: ${filters.entity_type}`);
    if (filters.actor_user_id) active.push(`Actor: ${filters.actor_user_id}`);
    if (filters.approval_status) active.push(`Approval: ${filters.approval_status}`);
    if (filters.approval_type) active.push(`Type: ${filters.approval_type}`);
    if (filters.date_from) active.push(`From: ${filters.date_from}`);
    if (filters.date_to) active.push(`To: ${filters.date_to}`);
    return active;
  }, [filters]);

  function setField(key, value) { setFilters((prev) => ({ ...prev, [key]: value })); }

  function renderLinks(row) {
    const links = row.links || {};
    const entries = Object.entries(links);
    if (!entries.length) return <span className="muted">-</span>;
    return <div className="row wrap">{entries.map(([key, href]) => <Link key={key} href={href} className="secondary" style={{ padding: '4px 8px', borderRadius: 8 }}>{key}</Link>)}</div>;
  }

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Audit Log</h1>
            <p className="muted">Review user actions, approval decisions, linked entities, and exception-heavy flows from one manager/admin workspace.</p>
          </div>
          {loading && <span className="badge info">Loading…</span>}
        </div>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <div className="card-grid" style={{ marginBottom: 14 }}>
          <div className="card"><div className="muted">Loaded audit rows</div><div className="kpi">{auditSummary.loaded}</div></div>
          <div className="card"><div className="muted">Potential exceptions</div><div className="kpi">{auditSummary.exceptions}</div></div>
          <div className="card"><div className="muted">Pending approvals</div><div className="kpi">{approvalSummary.pending}</div></div>
          <div className="card"><div className="muted">Approved</div><div className="kpi">{approvalSummary.approved}</div></div>
        </div>

        <form className="form-grid audit-filter-grid" onSubmit={(e) => { e.preventDefault(); loadAll(filters).catch(console.error); }}>
          <label className="field">Search<input value={filters.q} onChange={(e) => setField('q', e.target.value)} placeholder="order no, room, reason, decision note" /></label>
          <label className="field">Action<input value={filters.action} onChange={(e) => setField('action', e.target.value)} placeholder="refund.created" /></label>
          <label className="field">Entity<input value={filters.entity_type} onChange={(e) => setField('entity_type', e.target.value)} placeholder="order / refund / room_charge_posting" /></label>
          <label className="field">Actor User ID<input value={filters.actor_user_id} onChange={(e) => setField('actor_user_id', e.target.value)} /></label>
          <label className="field">Approval Status<select value={filters.approval_status} onChange={(e) => setField('approval_status', e.target.value)}><option value="">All</option><option value="pending">pending</option><option value="approved">approved</option></select></label>
          <label className="field">Approval Type<input value={filters.approval_type} onChange={(e) => setField('approval_type', e.target.value)} placeholder="refund / reopen_session / room_charge_write_off" /></label>
          <label className="field">Date From<input type="date" value={filters.date_from} onChange={(e) => setField('date_from', e.target.value)} /></label>
          <label className="field">Date To<input type="date" value={filters.date_to} onChange={(e) => setField('date_to', e.target.value)} /></label>
          <div className="row wrap" style={{ gridColumn: '1 / -1' }}>
            <button type="submit" className="primary">Apply Filters</button>
            <button type="button" className="secondary" onClick={() => {
              const blank = { q: '', action: '', entity_type: '', actor_user_id: '', date_from: '', date_to: '', approval_status: '', approval_type: '', limit: 200 };
              setFilters(blank);
              loadAll(blank).catch(console.error);
            }}>Reset</button>
          </div>
        </form>
        {!!activeFilters.length && (
          <div className="row wrap" style={{ marginTop: 8, gap: 6 }}>
            {activeFilters.map((filter, idx) => <span key={idx} className="badge info">{filter}</span>)}
          </div>
        )}
      </section>

      <section className="section">
        <div className="two-column-layout audit-review-layout">
          <div className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>Approvals review queue</strong>
              <span className="small muted">{approvals.length} rows</span>
            </div>
            <div className="stack-tight" style={{ marginTop: 10 }}>
              {approvals.map((row) => (
                <button key={row.id} type="button" className={`list-row-button ${selectedApproval?.id === row.id ? 'active' : ''}`} onClick={() => setSelectedApprovalId(row.id)}>
                  <div>
                    <div className="row wrap" style={{ gap: 8 }}>
                      <strong>{row.approval_type}</strong>
                      <span className={`badge ${row.status === 'approved' ? 'success' : 'warn'}`}>{row.status}</span>
                    </div>
                    <div className="small muted">{row.entity_type} #{row.entity_id || '-'}</div>
                    <div className="small muted">{row.requested_reason || 'No reason logged'}</div>
                  </div>
                </button>
              ))}
              {!approvals.length && <div className="muted">No approvals found.</div>}
            </div>
          </div>

          <div className="card">
            {!selectedApproval && <div className="muted">Select an approval to review details.</div>}
            {!!selectedApproval && (
              <div className="stack-tight">
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <strong>{selectedApproval.approval_type}</strong>
                    <div className="small muted">{selectedApproval.entity_type} #{selectedApproval.entity_id || '-'}</div>
                  </div>
                  <span className={`badge ${selectedApproval.status === 'approved' ? 'success' : 'warn'}`}>{selectedApproval.status}</span>
                </div>
                {selectedApproval.status === 'pending' && (
                  <div className="card" style={{ border: '2px solid var(--color-warn)', background: 'var(--color-warn-light)' }}>
                    <div className="muted">Pending Decision</div>
                    <div className="stack-tight">
                      <textarea value={decisionNote} onChange={(e) => setDecisionNote(e.target.value)} placeholder="Optional decision note" rows={2} />
                      <div className="row wrap" style={{ gap: 8 }}>
                        <button type="button" className="success" onClick={handleApprove}>Approve</button>
                        <button type="button" className="danger" onClick={handleReject}>Reject</button>
                      </div>
                    </div>
                  </div>
                )}
                <div className="form-grid-3">
                  <div className="card"><div className="muted">Requested by</div><strong>{selectedApproval.requested_by_name || '-'}</strong></div>
                  <div className="card"><div className="muted">Approved by</div><strong>{selectedApproval.approved_by_name || '-'}</strong></div>
                  <div className="card"><div className="muted">Requested at</div><strong>{selectedApproval.requested_at || '-'}</strong></div>
                </div>
                <div className="card"><div className="muted">Reason</div><div>{selectedApproval.requested_reason || '-'}</div></div>
                <div className="card"><div className="muted">Decision note</div><div>{selectedApproval.decision_note || '-'}</div></div>
                <div className="card"><div className="muted">Request details</div><pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 12 }}>{JSON.stringify(selectedApproval.request_details || {}, null, 2)}</pre></div>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="two-column-layout audit-review-layout">
          <div className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>Audit entries</strong>
              <span className="small muted">{rows.length} rows</span>
            </div>
            <div className="stack-tight" style={{ marginTop: 10 }}>
              {rows.map((row) => (
                <button key={row.id} type="button" className={`list-row-button ${selectedAudit?.id === row.id ? 'active' : ''}`} onClick={() => setSelectedAuditId(row.id)}>
                  <div>
                    <div className="row wrap" style={{ gap: 8 }}>
                      <strong>{row.action}</strong>
                      {Number(row.status_code || 200) >= 400 && <span className="badge danger">HTTP {row.status_code}</span>}
                    </div>
                    <div className="small muted">{formatDateTime(row.created_at)} · {row.actor_name || row.actor_username || '-'}</div>
                    <div className="small muted">{row.entity_type} #{row.entity_id || '-'}</div>
                  </div>
                </button>
              ))}
              {!rows.length && <div className="muted">No audit rows found.</div>}
            </div>
          </div>

          <div className="card">
            {!selectedAudit && <div className="muted">Select an audit entry to review full details.</div>}
            {!!selectedAudit && (
              <div className="stack-tight">
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <strong>{selectedAudit.action}</strong>
                    <div className="small muted">{selectedAudit.entity_type} #{selectedAudit.entity_id || '-'}</div>
                  </div>
                  <span className={`badge ${Number(selectedAudit.status_code || 200) >= 400 ? 'danger' : 'info'}`}>{selectedAudit.status_code || 'OK'}</span>
                </div>
                <div className="form-grid-3">
                  <div className="card"><div className="muted">Actor</div><strong>{selectedAudit.actor_name || selectedAudit.actor_username || '-'}</strong></div>
                  <div className="card"><div className="muted">Time</div><strong>{formatDateTime(selectedAudit.created_at)}</strong></div>
                  <div className="card"><div className="muted">Method</div><strong>{selectedAudit.request_method || '-'}</strong></div>
                </div>
                <div className="card"><div className="muted">Path</div><div>{selectedAudit.request_path || '-'}</div></div>
                <div className="card"><div className="muted">Linked records</div>{renderLinks(selectedAudit)}</div>
                <div className="card"><div className="muted">Details JSON</div><pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 12 }}>{JSON.stringify(selectedAudit.details || {}, null, 2)}</pre></div>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
