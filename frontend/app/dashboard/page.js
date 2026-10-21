'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { getDashboard } from '../../lib/api';
import PosIcon from '../../components/PosIcon';

const shortcuts = [
  ['/orders', 'Orders', 'Tickets, payments, and order history', 'orders'],
  ['/sessions', 'Shift Sessions', 'Open shifts and reconcile the drawer', 'shift'],
  ['/cash-movements', 'Cash Movements', 'Cash in, paid out, and safe drops', 'cash'],
  ['/sync', 'Sync Queue', 'Delivery status and retries', 'sync'],
];
function money(value) {
  return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
export default function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    getDashboard().then(setSummary).catch(err => setError(err.message || 'Failed to load dashboard.'));
  }, []);
  const metrics = [
    ['Open Sessions', summary?.open_sessions, 'shift', '/sessions'],
    ['Open Draft / Held Orders', summary?.orders_open, 'orders', '/orders'],
    ['Active Menu Items', summary?.catalog_count, 'menu', '/catalog'],
    ['Pending Sync', summary?.pending_sync, 'sync', '/sync'],
  ];
  return (
    <div className="stack pos-dashboard">
      <section className="dashboard-heading">
        <div><div className="eyebrow">Service overview</div><h1>Dashboard</h1></div>
        <Link href="/pos" className="button-link primary dashboard-open"><PosIcon name="terminal" />Open POS<PosIcon name="arrow" /></Link>
      </section>
      {!!error && <p className="error-text" role="alert">{error}</p>}
      <section className="sales-overview" aria-label="Today's sales">
        <div className="sales-feature"><div className="sales-feature-top"><span>Sales Today</span><PosIcon name="cash" /></div><strong>{summary ? money(summary.sales_today) : '—'}</strong><div className="sales-feature-bottom"><span>Hidden Oasis</span><span>Point of sale</span></div></div>
        <div className="cash-feature"><span className="summary-icon"><PosIcon name="cash" /></span><div><span>Cash In Today</span><strong>{summary ? money(summary.cash_today) : '—'}</strong></div><Link href="/cash-movements">View cash movements <span aria-hidden="true">↗</span></Link></div>
      </section>
      <section className="dashboard-metrics" aria-label="POS activity">{metrics.map(([label, value, icon, href]) => <Link href={href} key={label} className="dashboard-stat"><div><span>{label}</span><strong>{value ?? '—'}</strong></div><span className="summary-icon"><PosIcon name={icon} /></span></Link>)}</section>
      <section className="section dashboard-session">
        <div className="panel-title"><h2>Latest Session</h2><Link href="/sessions" className="subtle-link">View sessions ↗</Link></div>
        {summary?.latest_session ? <div className="session-summary">
          <div><span>Session</span><strong>{summary.latest_session.session_code}</strong></div>
          <div><span>Register</span><strong>{summary.latest_session.register_name || '—'}</strong></div>
          <div><span>Expected Cash</span><strong>{money(summary.latest_session.closing_expected_cash)}</strong></div>
          <div><span>Status</span><strong><span className={`badge ${summary.latest_session.status === 'open' ? 'success' : 'info'}`}>{summary.latest_session.status}</span></strong></div>
        </div> : <p className="muted">{summary ? 'No session data yet.' : 'Loading session…'}</p>}
      </section>
      <section className="dashboard-shortcuts" aria-label="Shortcuts">{shortcuts.map(([href, label, note, icon]) => <Link key={href} href={href} className="dashboard-shortcut"><span className="summary-icon"><PosIcon name={icon} /></span><div><strong>{label}</strong><span>{note}</span></div><PosIcon name="arrow" /></Link>)}</section>
    </div>
  );
}
