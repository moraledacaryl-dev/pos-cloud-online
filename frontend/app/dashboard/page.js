'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { getDashboard } from '../../lib/api';

const shortcuts = [
  ['/pos', 'Open POS', 'Start cashier workflow and accept payments quickly.'],
  ['/orders', 'Orders', 'Review ticket history, tenders, and cashier notes.'],
  ['/sessions', 'Shift Sessions', 'Open, monitor, and close register shifts.'],
  ['/cash-movements', 'Cash Movements', 'Paid in, paid out, float, and drawer control.'],
  ['/sync', 'Sync Queue', 'Review pending sales and drawer events before accounting ingestion.'],
];

function money(value) {
  return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getDashboard().then(setSummary).catch((err) => setError(err.message || 'Failed to load dashboard.'));
  }, []);

  return (
    <div className="stack">
      <section className="section">
        <h1>Dashboard</h1>
        <p className="muted">Live view of POS activity, open shifts, sales, and accounting sync status.</p>
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <div className="metric-rail">
          <div className="metric-card"><div className="muted">Open Sessions</div><div className="metric-value">{summary?.open_sessions ?? '-'}</div></div>
          <div className="metric-card"><div className="muted">Pending Sync</div><div className="metric-value">{summary?.pending_sync ?? '-'}</div></div>
          <div className="metric-card"><div className="muted">Sales Today</div><div className="metric-value">{summary ? money(summary.sales_today) : '-'}</div></div>
          <div className="metric-card"><div className="muted">Cash In Today</div><div className="metric-value">{summary ? money(summary.cash_today) : '-'}</div></div>
          <div className="metric-card"><div className="muted">Open Draft / Held Orders</div><div className="metric-value">{summary?.orders_open ?? '-'}</div></div>
          <div className="metric-card"><div className="muted">Active Menu Items</div><div className="metric-value">{summary?.catalog_count ?? '-'}</div></div>
        </div>
      </section>

      <section className="section">
        <h2>Latest Session</h2>
        {summary?.latest_session ? (
          <div className="card-grid" style={{ marginTop: 10 }}>
            <div className="card"><div className="muted">Session</div><div className="metric-value" style={{ fontSize: 22 }}>{summary.latest_session.session_code}</div></div>
            <div className="card"><div className="muted">Register</div><div className="metric-value" style={{ fontSize: 22 }}>{summary.latest_session.register_name || '-'}</div></div>
            <div className="card"><div className="muted">Expected Cash</div><div className="metric-value" style={{ fontSize: 22 }}>{money(summary.latest_session.closing_expected_cash)}</div></div>
            <div className="card"><div className="muted">Status</div><div className="metric-value" style={{ fontSize: 22 }}>{summary.latest_session.status}</div></div>
          </div>
        ) : <p className="muted" style={{ marginTop: 8 }}>No session data yet.</p>}
      </section>

      <section className="section">
        <h2>Shortcuts</h2>
        <div className="card-grid" style={{ marginTop: 10 }}>
          {shortcuts.map(([href, label, note]) => (
            <Link key={href} href={href} className="card card-link">
              <div className="row" style={{ justifyContent: 'space-between' }}><strong>{label}</strong><span>→</span></div>
              <div className="small muted">{note}</div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
