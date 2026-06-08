'use client';

import { useEffect, useState } from 'react';
import { fetchCustomerDisplaySnapshot } from '../../lib/api';

const DISPLAY_KEY = 'pos_customer_display';

function money(value) {
  return `P${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function readDisplaySnapshot() {
  if (typeof window === 'undefined') return null;
  try {
    return JSON.parse(window.localStorage.getItem(DISPLAY_KEY) || 'null');
  } catch {
    return null;
  }
}

export default function CustomerDisplayPage() {
  const [latest, setLatest] = useState(null);
  const [serverConnected, setServerConnected] = useState(false);

  useEffect(() => {
    let active = true;
    const channel = new URLSearchParams(window.location.search).get('channel') || 'main';
    const load = async () => {
      try {
        const snapshot = await fetchCustomerDisplaySnapshot(channel);
        if (!active) return;
        setLatest(snapshot || readDisplaySnapshot());
        setServerConnected(true);
      } catch {
        if (!active) return;
        setLatest(readDisplaySnapshot());
        setServerConnected(false);
      }
    };
    const onStorage = (event) => {
      if (event.key === DISPLAY_KEY && !serverConnected) setLatest(readDisplaySnapshot());
    };
    load().catch(console.error);
    window.addEventListener('storage', onStorage);
    const timer = window.setInterval(() => load().catch(console.error), 1000);
    return () => {
      active = false;
      window.removeEventListener('storage', onStorage);
      window.clearInterval(timer);
    };
  }, [serverConnected]);

  const cart = latest?.cart || [];
  const totals = latest?.totals || {};

  return (
    <div className="customer-display">
      <header className="customer-display-header">
        <div>
          <p className="customer-display-eyebrow">Hidden Oasis</p>
          <h1>{latest?.order_no || 'Welcome'}</h1>
          <p>{latest ? `${latest.guest_name || 'Walk-in Guest'} / ${latest.table_label || 'Counter'}` : 'Your order will appear here.'}</p>
        </div>
        <div className={`customer-display-live ${serverConnected ? '' : 'fallback'}`}><span /> {serverConnected ? 'Live order' : 'Local display fallback'}</div>
      </header>

      {!cart.length ? (
        <section className="customer-display-empty">
          <h2>Ready when you are</h2>
          <p>Items will appear as your cashier adds them.</p>
        </section>
      ) : (
        <div className="customer-display-layout">
          <section className="customer-display-lines" aria-label="Current order items">
            {cart.map((line) => (
              <div className="customer-display-line" key={line.local_id}>
                <div>
                  <strong>{line.quantity} x {line.name}</strong>
                  {!!line.note && <p>{line.note}</p>}
                </div>
                <strong>{money(line.total)}</strong>
              </div>
            ))}
          </section>
          <aside className="customer-display-total">
            <p>Your total</p>
            <strong>{money(totals.total)}</strong>
            {!!totals.discount && <span>You saved {money(totals.discount)}</span>}
            <small>Please check your order before payment.</small>
          </aside>
        </div>
      )}
    </div>
  );
}
