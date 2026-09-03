'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { API_BASE, errorMessage, fetchCustomerDisplaySnapshot, request } from '../../lib/api';
import { useCurrentUser } from '../../lib/useCurrentUser';

const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });

function SetupCard({ mode, children }) {
  return (
    <section className="customer-display-empty customer-display-setup">
      <div className="customer-display-setup-card">
        <div className="customer-display-setup-brand" aria-hidden="true">HO</div>
        <div className="customer-display-setup-heading">
          <p className="customer-display-eyebrow">Hidden Oasis · Display setup</p>
          <span className="customer-display-mode">{mode}</span>
        </div>
        {children}
      </div>
    </section>
  );
}

function displayTime(value) {
  if (!value) return 'Never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown';
  return date.toLocaleString('en-PH', { dateStyle: 'medium', timeStyle: 'short' });
}

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
  const [devices, setDevices] = useState([]);
  const [devicesBusy, setDevicesBusy] = useState(false);

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

  async function loadDevices() {
    setDevicesBusy(true);
    try {
      const rows = await request('/customer-display/devices');
      const now = Date.now();
      setDevices(Array.isArray(rows) ? rows.map((device) => ({
        ...device,
        display_active: !!device.is_active && (!device.expires_at || new Date(device.expires_at).getTime() > now),
      })) : []);
    } catch (err) {
      setError(err.message || 'Could not load paired displays.');
    } finally {
      setDevicesBusy(false);
    }
  }

  useEffect(() => {
    if (!managerSetup || !identityLoaded || !user || !can('approvals.manage')) return;
    loadDevices().catch(() => {});
  }, [managerSetup, identityLoaded, user]);

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

  async function revokeDisplay(device) {
    if (!device?.device_uuid) return;
    setDevicesBusy(true);
    setError('');
    try {
      await postJson(`/customer-display/devices/${encodeURIComponent(device.device_uuid)}/revoke`, {});
      await loadDevices();
    } catch (err) {
      setError(err.message || 'Could not revoke this display.');
      setDevicesBusy(false);
    }
  }

  const cart = latest?.cart || [];
  const totals = latest?.totals || {};

  if (managerSetup) {
    if (!identityLoaded) {
      return <main className="customer-display"><SetupCard mode="Manager setup"><div aria-live="polite" aria-busy="true"><h1>Checking manager access…</h1><p className="customer-display-setup-copy">Confirming that this account can create a secure pairing code.</p></div></SetupCard></main>;
    }
    if (!user || !can('approvals.manage')) {
      return (
        <main className="customer-display">
          <SetupCard mode="Manager setup">
            <h1>Manager sign-in required</h1>
            <p className="customer-display-setup-copy">Only a manager or owner can connect a new customer-facing screen.</p>
            <div className="customer-display-actions">
              <Link className="button-link" href={`/login?next=${encodeURIComponent(`/customer-display?setup=1&channel=${channel}`)}`}>Sign in as manager</Link>
              <Link className="customer-display-text-link" href="/pos">Return to POS</Link>
            </div>
          </SetupCard>
        </main>
      );
    }
    return (
      <main className="customer-display">
        <SetupCard mode="Manager setup">
          <h1>Connect a customer screen</h1>
          <p className="customer-display-setup-copy">This optional screen shows guests their order and total. It is separate from the cashier POS.</p>
          <ol className="customer-display-steps">
            <li><span>1</span><div><strong>Open the customer screen</strong><small>Use a second monitor, tablet, or browser window.</small></div></li>
            <li><span>2</span><div><strong>Generate a temporary code</strong><small>The code can be used once and expires quickly.</small></div></li>
            <li><span>3</span><div><strong>Enter the code there</strong><small>The screen will then follow channel <b>{channel}</b>.</small></div></li>
          </ol>
          {generatedCode ? (
            <div className="customer-display-code-panel" aria-live="polite">
              <span>One-time pairing code</span>
              <strong>{generatedCode.pairing_code}</strong>
              <small>Enter it within {generatedCode.expires_in_seconds} seconds. It works once only.</small>
            </div>
          ) : (
            <button type="button" className="primary customer-display-primary-action" onClick={generatePairingCode} disabled={busy}>{busy ? 'Generating code…' : 'Generate pairing code'}</button>
          )}
          {!!generatedCode && <button type="button" className="secondary customer-display-primary-action" onClick={generatePairingCode} disabled={busy}>{busy ? 'Generating code…' : 'Generate a new code'}</button>}
          {!!error && <p className="customer-display-error" role="alert">{error}</p>}
          <div className="customer-display-footer-actions">
            <a className="customer-display-text-link" href={`/customer-display?channel=${encodeURIComponent(channel)}`} target="_blank" rel="noreferrer">Open customer screen ↗</a>
            <Link className="customer-display-text-link" href="/pos">Not using a customer display? Return to POS</Link>
          </div>
          <section className="customer-display-devices" aria-labelledby="paired-displays-heading">
            <div className="customer-display-devices-heading">
              <div>
                <h2 id="paired-displays-heading">Paired displays</h2>
                <p>Review connected screens and revoke any device you no longer recognize or use.</p>
              </div>
              <button type="button" className="secondary" onClick={() => loadDevices()} disabled={devicesBusy}>{devicesBusy ? 'Refreshing…' : 'Refresh'}</button>
            </div>
            {!devicesBusy && !devices.length && <p className="customer-display-no-devices">No displays have been paired yet.</p>}
            {!!devices.length && (
              <div className="customer-display-device-list">
                {devices.map((device) => {
                  const active = device.display_active;
                  return (
                    <article className="customer-display-device" key={device.device_uuid}>
                      <div>
                        <div className="customer-display-device-title"><strong>{device.channel || 'main'}</strong><span className={active ? 'active' : 'inactive'}>{active ? 'Active' : device.revoked_at ? 'Revoked' : 'Expired'}</span></div>
                        <small>Device {String(device.device_uuid).slice(0, 8)} · Last seen {displayTime(device.last_seen_at)}</small>
                      </div>
                      <button type="button" className="secondary" disabled={!active || devicesBusy} onClick={() => revokeDisplay(device)}>{active ? 'Revoke' : 'Unavailable'}</button>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </SetupCard>
      </main>
    );
  }

  if (needsPairing) {
    return (
      <main className="customer-display">
        <SetupCard mode="Customer screen">
          <h1>Connect this display</h1>
          <p className="customer-display-setup-copy">This is the optional guest-facing screen—not the cashier terminal. Ask a manager to generate a pairing code.</p>
          <form className="customer-display-pair-form" onSubmit={activateDisplay}>
            <label htmlFor="customer-display-pairing-code">One-time pairing code</label>
            <input
              id="customer-display-pairing-code"
              aria-label="Pairing code"
              autoComplete="one-time-code"
              inputMode="text"
              maxLength={24}
              value={pairingCode}
              onChange={(event) => setPairingCode(event.target.value.toUpperCase())}
              placeholder="Enter the code from your manager"
            />
            <button type="submit" className="primary" disabled={busy || pairingCode.trim().length < 8}>{busy ? 'Pairing…' : 'Pair display'}</button>
          </form>
          {!!error && <p className="customer-display-error" role="alert">{error}</p>}
          <div className="customer-display-help">
            <strong>Need a code?</strong>
            <span>On a manager device, open Customer Display Setup and choose Generate pairing code.</span>
          </div>
          <div className="customer-display-footer-actions">
            {user && can('approvals.manage') && <Link className="customer-display-text-link" href={`/customer-display?setup=1&channel=${encodeURIComponent(channel)}`}>Open manager setup</Link>}
            {user && <Link className="customer-display-text-link" href="/pos">Return to POS</Link>}
          </div>
        </SetupCard>
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
