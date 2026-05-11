'use client';

import { useEffect, useState } from 'react';
import { fetchOrders } from '../../lib/api';

export default function CustomerDisplayPage() {
  const [latest, setLatest] = useState(null);
  useEffect(() => {
    const load = async () => {
      const rows = await fetchOrders({ limit: 1 });
      setLatest(Array.isArray(rows) && rows.length ? rows[0] : null);
    };
    load().catch(() => {});
    const t = setInterval(() => load().catch(() => {}), 4000);
    return () => clearInterval(t);
  }, []);
  return (
    <div style={{ minHeight: '100vh', background: '#111827', color: 'white', padding: 32 }}>
      <h1 style={{ fontSize: 48, marginBottom: 8 }}>Customer Display</h1>
      <p style={{ color: '#9ca3af', marginBottom: 24 }}>Mirror this on a second screen for guests.</p>
      {!latest && <div style={{ fontSize: 24 }}>No active order yet.</div>}
      {latest && (
        <div style={{ display: 'grid', gap: 16 }}>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{latest.order_no}</div>
          <div style={{ fontSize: 20 }}>{latest.guest_name || 'Walk-in Guest'} · {latest.table_label || 'Counter'}</div>
          <div style={{ fontSize: 18 }}>Total: ₱{Number(latest.total_amount || 0).toFixed(2)}</div>
          <div style={{ fontSize: 18 }}>Settled: ₱{Number((latest.settled_amount ?? latest.paid_amount) || 0).toFixed(2)}</div>
          <div style={{ fontSize: 18 }}>Folio Pending: ₱{Number(latest.folio_pending_amount || 0).toFixed(2)}</div>
          <div style={{ fontSize: 18 }}>Balance: ₱{Number(latest.balance_due || 0).toFixed(2)}</div>
        </div>
      )}
    </div>
  );
}
