'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { API_BASE, errorMessage, fetchCustomerDisplaySnapshot } from '../../lib/api';
import { useCurrentUser } from '../../lib/useCurrentUser';

const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });

function csrfToken() {
  if (typeof document === 'undefined') return '';
  const row = document.cookie.split('; ').find((part) => part.startsWith('pos_csrf='));
  return row ? decodeURIComponent(row.slice('pos_csrf='.length)) : '';
}

async function postJson(path, payload) {
  const headers = { 'Content-Type': 'application/json' };
  const csrf = csrfToken();
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers,
    body: JSON.stringify(payload),
  });
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  if (!res.ok) throw new Error(errorMessage(data));
  return data;
}

export default function CustomerDisplayPage() {
  const { loaded: identityLoaded, user, can } = useCurrentUser();
  const [latest, setLatest] = useState(null);
  const [serverConnected, setServerConnected] = useState(false);
  const [needsPairing, setNeedsPairing] = useState(false);
  const [pairingCode, setPairingCode] = useState('');
  const [generatedCode, setGeneratedCode] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [channel, setChannel] = useState('main');
  const [managerSetup, setManagerSetup] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setChannel(params.get('channel') || 'main');
    setManagerSetup(params.get('setup') === '1');
  }, []);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const snapshot = await fetchCustomerDisplaySnapshot(channel);
        if (!active) return;
        setLatest(snapshot || null);
        setServerConnected(true);
        setNeedsPairing(false);
      } catch (err) {
        if (!active) return;
        setLatest(null);
        setServerConnected(false);
        setNeedsPairing(true);
      }
    };
    load().catch(() => {});
    const timer = window.setInterval(() => load().catch(() => {}), 1000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [channel]);

  async function activateDisplay(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await postJson('/customer-display/activate', { pairing_code: pairingCode });
      setPairingCode('');
      setNeedsPairing(false);
      const snapshot = await fetchCustomerDisplaySnapshot(channel);
      setLatest(snapshot || null);
      setServerConnected(true);
    } catch (err) {
      setError(err.message || 'Pairing failed.');
    } finally {
      setBusy(false);
    }
  }

  async function generatePairingCode() {
    setBusy(true);
    setError('');
    try {
      const result = await postJson('/customer-display/pairing-code', { channel });
      setGeneratedCode(result);
    } catch (err) {
      setError(err.message || 'Manager authorization is required to create a pairing code.');
    } finally {
      setBusy(false);
    }
  }

  const cart = latest?.cart || [];
  const totals = latest?.totals || {};

  if (managerSetup) {
    if (!identityLoaded) {
      return <main className="customer-display"><section className="customer-display-empty" aria-live="polite"><p className="customer-display-eyebrow">Hidden Oasis</p><h1>Checking manager access…</h1></section></main>;
    }
    if (!user || !can('approvals.manage')) {
      return <main className="customer-display"><section className="customer-display-empty"><p className="customer-display-eyebrow">Hidden Oasis</p><h1>Manager sign-in required</h1><p>A manager or owner must sign in before creating a customer-display pairing code.</p><Link className="button-link" href={`/login?next=${encodeURIComponent(`/customer-display?setup=1&channel=${channel}`)}`}>Sign in as manager</Link></section></main>;
    }
    return (
      <main className="customer-display">
        <section className="customer-display-empty">
          <p className="customer-display-eyebrow">Hidden Oasis</p>
          <h1>Pair customer display</h1>
          <p>Channel: <strong>{channel}</strong></p>
          <button type="button" className="primary" onClick={generatePairingCode} disabled={busy}>Generate one-time pairing code</button>
          {generatedCode && (
            <div>
              <h2>{generatedCode.pairing_code}</h2>
              <p>Enter this code on the customer display within {generatedCode.expires_in_seconds} seconds. It works once only.</p>
            </div>
          )}
          {!!error && <p className="error-text">{error}</p>}
        </section>
      </main>
    );
  }

  if (needsPairing) {
    return (
      <main className="customer-display">
        <section className="customer-display-empty">
          <p className="customer-display-eyebrow">Hidden Oasis</p>
          <h1>Display pairing required</h1>
          <p>This screen must be paired by a manager before it can show an order.</p>
          <form onSubmit={activateDisplay} style={{ display: 'grid', gap: 12, width: 'min(420px, 100%)' }}>
            <input
              aria-label="Pairing code"
              autoComplete="one-time-code"
              value={pairingCode}
              onChange={(event) => setPairingCode(event.target.value.toUpperCase())}
              placeholder="Enter pairing code"
            />
            <button type="submit" className="primary" disabled={busy || pairingCode.trim().length < 8}>{busy ? 'Pairing…' : 'Pair display'}</button>
          </form>
          {!!error && <p className="error-text">{error}</p>}
        </section>
      </main>
    );
  }

  return (
    <main className="customer-display">
      <header className="customer-display-header">
        <div>
          <p className="customer-display-eyebrow">Hidden Oasis</p>
          <h1>{latest?.order_no || 'Welcome'}</h1>
          <p>{latest?.table_label || 'Your order will appear here.'}</p>
        </div>
        <div className={`customer-display-live ${serverConnected ? '' : 'fallback'}`}><span /> {serverConnected ? 'Live order' : 'Reconnecting'}</div>
      </header>

      {!cart.length ? (
        <section className="customer-display-empty">
          <h2>Ready when you are</h2>
          <p>Items will appear as your cashier adds them.</p>
        </section>
      ) : (
        <div className="customer-display-layout">
          <section className="customer-display-lines" aria-label="Current order items">
            {cart.map((line, index) => (
              <div className="customer-display-line" key={`${line.name}-${index}`}>
                <div><strong>{line.quantity} × {line.name}</strong></div>
                <strong>{peso.format(Number(line.total || 0))}</strong>
              </div>
            ))}
          </section>
          <aside className="customer-display-total">
            <p>Your total</p>
            <strong>{peso.format(Number(totals.total || 0))}</strong>
            {!!totals.discount && <span>You saved {peso.format(Number(totals.discount || 0))}</span>}
            <small>Please check your order before payment.</small>
          </aside>
        </div>
      )}
    </main>
  );
}
