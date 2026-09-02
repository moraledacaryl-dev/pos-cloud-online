'use client';

import { useEffect, useId, useState } from 'react';
import { useDialogFocus } from '../lib/useDialogFocus';

export default function ManagerOverrideModal({ open, title = 'Manager Override', subtitle = '', actionLabel = 'Approve', onApprove, onClose }) {
  const titleId = useId();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setUsername('');
    setPassword('');
    setError('');
    setLoading(false);
  }, [open]);

  useDialogFocus(open, () => { if (!loading) onClose?.(); });

  if (!open) return null;

  async function handleApprove(event) {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (!username.trim() || !password) throw new Error('Manager username and password are required.');
      // Credentials are used once by the action-specific approval endpoint. They
      // are never converted client-side into an approver user ID and are never
      // stored in localStorage/sessionStorage.
      await onApprove?.({ id: { manager_username: username.trim(), manager_password: password } });
      onClose?.();
    } catch (e) {
      setError(e.message || 'Override failed.');
    } finally {
      setPassword('');
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
      <div className="modal-card" style={{ maxWidth: 440 }}>
        <div className="modal-header">
          <div><h2 id={titleId}>{title}</h2>{!!subtitle && <p className="muted">{subtitle}</p>}</div>
          <button type="button" className="secondary" onClick={onClose} disabled={loading}>Close</button>
        </div>
        <form className="modal-form stack-tight" onSubmit={handleApprove}>
          <label className="field">Manager Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" /></label>
          <label className="field">Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
          {!!error && <p className="error-text">{error}</p>}
          <div className="row wrap">
            <button type="submit" className="primary" disabled={loading}>{loading ? 'Authorizing...' : actionLabel}</button>
            <button type="button" className="secondary" onClick={onClose} disabled={loading}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}
