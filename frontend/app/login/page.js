'use client';

import { useState } from 'react';
import { bootstrap, login } from '../../lib/api';

const SHOW_DEVELOPMENT_BOOTSTRAP = process.env.NEXT_PUBLIC_ENABLE_ADMIN_BOOTSTRAP === 'true';


export default function LoginPage() {
  const [form, setForm] = useState({ username: '', password: '' });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleBootstrap() {
    setError(''); setNotice(''); setLoading(true);
    try { await bootstrap(); setNotice('Development bootstrap completed.'); }
    catch (e) { setError(e.message || 'Bootstrap failed.'); }
    finally { setLoading(false); }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(''); setNotice(''); setLoading(true);
    try {
      await login(form);
      const searchParams = new URLSearchParams(window.location.search);
      const next = searchParams.get('next') || '/dashboard';
      window.location.href = next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard';
    } catch (e) { setError(e.message || 'Invalid username or password.'); }
    finally { setLoading(false); }
  }

  return (
    <main className="pos-login"><div className="login-identity" aria-hidden="true"><div className="login-wordmark">Hidden Oasis <span>POS</span></div><div className="login-orbit"><span /><span /><span /><div className="login-symbol">HO<span>POINT OF SALE</span></div></div><div className="login-identity-footer"><span>Orders</span><span>Service</span><span>Payments</span></div></div>
      <section className="pos-login-card">
        <div className="login-small-mark">HO</div>
        <div><div className="eyebrow">Hidden Oasis POS</div><h1>Welcome back.</h1></div>
        <p className="muted">Sign in to your workstation.</p>
        <form className="login-form" onSubmit={handleSubmit}>
          <label className="field">Username<input  autoComplete="username" value={form.username} onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))} /></label>
          <label className="field">Password<input  autoComplete="current-password" type="password" value={form.password} onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))} /></label>
          <button type="submit" className="primary" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
          {SHOW_DEVELOPMENT_BOOTSTRAP && <button type="button" className="secondary" onClick={handleBootstrap} disabled={loading}>Bootstrap admin</button>}
          {!!notice && <p className="notice-text">{notice}</p>}
          {!!error && <p className="error-text">{error}</p>}
        </form>
        <small className="login-credit">Hidden Oasis · Staff access</small>
      </section>
    </main>
  );
}
