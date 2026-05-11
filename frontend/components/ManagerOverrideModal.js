'use client';
import { useEffect, useState } from 'react';
import { login } from '../lib/api';
export default function ManagerOverrideModal({ open, title = 'Manager Override', subtitle = '', actionLabel = 'Approve', onApprove, onClose }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  useEffect(() => { if (open) { setUsername(''); setPassword(''); setError(''); setLoading(false); } }, [open]);
  if (!open) return null;
  async function handleApprove(event) {
    event.preventDefault(); setError(''); setLoading(true);
    try {
      const auth = await login({ username, password });
      const user = auth?.user || {};
      const roleCodes = new Set((user.roles || []).map((role) => role.code));
      const perms = new Set(user.permissions || []);
      if (!(roleCodes.has('owner') || roleCodes.has('manager') || user.role === 'owner' || user.role === 'manager' || perms.has('orders.void') || perms.has('catalog.manage'))) throw new Error('Override requires an owner or manager account.');
      await onApprove?.(user); onClose?.();
    } catch (e) { setError(e.message || 'Override failed.'); } finally { setLoading(false); }
  }
  return (<div className="modal-backdrop"><div className="modal-card" style={{ maxWidth: 440 }}><div className="modal-header"><div><h2>{title}</h2>{!!subtitle && <p className="muted">{subtitle}</p>}</div><button type="button" className="secondary" onClick={onClose}>Close</button></div><form className="modal-form stack-tight" onSubmit={handleApprove}><label className="field">Manager Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus /></label><label className="field">Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>{!!error && <p className="error-text">{error}</p>}<div className="row wrap"><button type="submit" className="primary" disabled={loading}>{loading ? 'Checking...' : actionLabel}</button><button type="button" className="secondary" onClick={onClose}>Cancel</button></div></form></div></div>);
}
