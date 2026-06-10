'use client';

import { useState } from 'react';
import { bootstrap, login, setRefreshToken, setToken } from '../../lib/api';

const SHOW_DEVELOPMENT_BOOTSTRAP = process.env.NEXT_PUBLIC_ENABLE_ADMIN_BOOTSTRAP === 'true';

export default function LoginPage() {
  const [form, setForm] = useState({ username: '', password: '' });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleBootstrap() {
    setError('');
    setNotice('');
    setLoading(true);
    try {
      const res = await bootstrap();
      setNotice(`Bootstrap ready: ${res.default_admin}`);
    } catch (e) {
      setError(e.message || 'Bootstrap failed.');
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setNotice('');
    setLoading(true);
    try {
      const res = await login(form);
      setToken(res.access_token);
      if (res.refresh_token) setRefreshToken(res.refresh_token);
      const searchParams = new URLSearchParams(window.location.search);
      const next = searchParams.get('next') || '/dashboard';
      window.location.href = next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard';
    } catch (e) {
      setError(e.message || 'Invalid username or password.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack login-stack">
      <section className="section login-panel">
        <div className="login-mark">HO</div>
        <h1>POS</h1>
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="field">
            Username
            <input autoComplete="username" value={form.username} onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))} />
          </label>
          <label className="field">
            Password
            <input autoComplete="current-password" type="password" value={form.password} onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))} />
          </label>
          <button type="submit" className="primary" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
          {SHOW_DEVELOPMENT_BOOTSTRAP && <button type="button" className="secondary" onClick={handleBootstrap} disabled={loading}>Bootstrap admin</button>}
          {!!notice && <p className="notice-text">{notice}</p>}
          {!!error && <p className="error-text">{error}</p>}
        </form>
        <small className="muted">by C.M.</small>
      </section>
    </div>
  );
}
