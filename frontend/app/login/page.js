'use client';

import { useState } from 'react';
import { bootstrap, login } from '../../lib/api';

const SHOW_DEVELOPMENT_BOOTSTRAP = process.env.NEXT_PUBLIC_ENABLE_ADMIN_BOOTSTRAP === 'true';

const styles = {
  shell: { minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: 'radial-gradient(circle at top left, #f8fbf9 0, transparent 32%), radial-gradient(circle at bottom right, #eef2f8 0, transparent 28%), #f6f6f4' },
  card: { width: 'min(480px, 100%)', display: 'grid', gap: 20, padding: 'clamp(30px, 4vw, 42px)', borderRadius: 24, border: '1px solid #e1e6df', background: 'rgba(255,255,255,.94)', boxShadow: '0 28px 80px rgba(26,38,30,.11)' },
  mark: { width: 56, height: 56, display: 'grid', placeItems: 'center', borderRadius: 17, background: '#243b68', color: '#fff', fontWeight: 720, letterSpacing: '.03em' },
  title: { margin: 0, fontSize: 38, letterSpacing: '-.04em', lineHeight: 1 },
  context: { margin: '-10px 0 0', color: '#676e68', fontSize: 14 },
  form: { display: 'grid', gap: 13 },
  label: { display: 'grid', gap: 6, fontSize: 12, fontWeight: 650, color: '#565b55' },
  input: { width: '100%', minHeight: 48, padding: '12px 13px', borderRadius: 12, border: '1px solid #d7dad4', background: '#fff' },
  button: { width: '100%', minHeight: 48, padding: '12px 13px', borderRadius: 12, border: '1px solid #111', background: '#111', color: '#fff', fontWeight: 650, cursor: 'pointer' },
  secondary: { width: '100%', padding: '10px 12px', borderRadius: 12, border: '1px solid #d7dad4', background: '#fff', color: '#111', fontWeight: 650, cursor: 'pointer' },
  credit: { color: '#7b8179', fontSize: 12 },
  error: { color: '#b42318', fontSize: 13, margin: 0 },
  notice: { color: '#1f6a47', fontSize: 13, margin: 0 },
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
