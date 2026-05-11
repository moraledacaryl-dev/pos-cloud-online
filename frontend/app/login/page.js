'use client';

import { useState } from 'react';
import { bootstrap, login, setRefreshToken, setToken } from '../../lib/api';

export default function LoginPage() {
  const [form, setForm] = useState({ username: 'admin', password: 'admin123' });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleBootstrap() {
    setError('');
    setNotice('');
    setLoading(true);
    try {
      const res = await bootstrap();
      setNotice(`Bootstrap ready. Login with ${res.default_admin} / ${res.default_password}`);
    } catch (e) {
      setError(e.message || 'Failed to bootstrap default admin.');
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
      window.location.href = '/dashboard';
    } catch (e) {
      setError(e.message || 'Failed to login.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack" style={{ maxWidth: 520, margin: '0 auto' }}>
      <section className="section">
        <h1>POS Cloud</h1>
        <p className="muted">Fast cashier operations, clean drawer control, and future-safe accounting sync.</p>
      </section>
      <section className="section">
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="field">
            Username
            <input value={form.username} onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))} />
          </label>
          <label className="field">
            Password
            <input type="password" value={form.password} onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))} />
          </label>
          <div className="row wrap">
            <button type="submit" className="primary" disabled={loading}>{loading ? 'Logging in...' : 'Login'}</button>
            <button type="button" className="secondary" onClick={handleBootstrap} disabled={loading}>Bootstrap default admin</button>
          </div>
          {!!notice && <p className="notice-text">{notice}</p>}
          {!!error && <p className="error-text">{error}</p>}
        </form>
      </section>
    </div>
  );
}
