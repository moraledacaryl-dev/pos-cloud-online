'use client';

import { useState } from 'react';
import { bootstrap, login } from '../../lib/api';

const SHOW_DEVELOPMENT_BOOTSTRAP = process.env.NEXT_PUBLIC_ENABLE_ADMIN_BOOTSTRAP === 'true';

const styles = {
  shell: { minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: '#e8ece8' },
  card: { width: 'min(480px, 100%)', display: 'grid', gap: 20, padding: 'clamp(30px, 4vw, 42px)', borderRadius: 22, border: '1px solid #bdc9c2', background: '#f8faf8', boxShadow: '0 24px 64px rgba(18,43,37,.13)' },
  mark: { width: 56, height: 56, display: 'grid', placeItems: 'center', borderRadius: 16, background: '#14523e', color: '#fff', fontWeight: 760, letterSpacing: '.03em', boxShadow: '0 10px 24px rgba(20,82,62,.2)' },
  title: { margin: 0, fontSize: 38, letterSpacing: '-.04em', lineHeight: 1 },
  context: { margin: '-10px 0 0', color: '#5b6862', fontSize: 14 },
  form: { display: 'grid', gap: 13 },
  label: { display: 'grid', gap: 6, fontSize: 12, fontWeight: 650, color: '#43534c' },
  input: { width: '100%', minHeight: 48, padding: '12px 13px', borderRadius: 11, border: '1px solid #bdc9c2', background: '#fff', color: '#122b25' },
  button: { width: '100%', minHeight: 48, padding: '12px 13px', borderRadius: 11, border: '1px solid #14523e', background: '#14523e', color: '#fff', fontWeight: 680, cursor: 'pointer' },
  secondary: { width: '100%', padding: '10px 12px', borderRadius: 11, border: '1px solid #bdc9c2', background: '#f8faf8', color: '#122b25', fontWeight: 650, cursor: 'pointer' },
  credit: { color: '#66756e', fontSize: 12 },
  error: { color: '#b9472f', fontSize: 13, margin: 0 },
  notice: { color: '#14523e', fontSize: 13, margin: 0 },
};

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
    <main style={styles.shell}>
      <section style={styles.card}>
        <div style={styles.mark}>HO</div>
        <h1 style={styles.title}>POS</h1>
        <p style={styles.context}>Hidden Oasis · Authorized resort workstation</p>
        <form style={styles.form} onSubmit={handleSubmit}>
          <label style={styles.label}>Username<input style={styles.input} autoComplete="username" value={form.username} onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))} /></label>
          <label style={styles.label}>Password<input style={styles.input} autoComplete="current-password" type="password" value={form.password} onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))} /></label>
          <button type="submit" style={styles.button} disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
          {SHOW_DEVELOPMENT_BOOTSTRAP && <button type="button" style={styles.secondary} onClick={handleBootstrap} disabled={loading}>Bootstrap admin</button>}
          {!!notice && <p style={styles.notice}>{notice}</p>}
          {!!error && <p style={styles.error}>{error}</p>}
        </form>
        <small style={styles.credit}>by C.M.</small>
      </section>
    </main>
  );
}
