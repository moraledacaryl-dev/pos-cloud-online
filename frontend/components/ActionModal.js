'use client';

import { useEffect, useId, useState } from 'react';

export default function ActionModal({
  open,
  title,
  description = '',
  fieldLabel = 'Reason',
  showField = true,
  defaultValue = '',
  required = false,
  inputType = 'textarea',
  min,
  max,
  confirmLabel = 'Confirm',
  tone = 'danger',
  onConfirm,
  onClose,
}) {
  const titleId = useId();
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setValue(String(defaultValue ?? ''));
    setError('');
    setBusy(false);
  }, [defaultValue, open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !busy) onClose?.();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [busy, onClose, open]);

  if (!open) return null;

  async function submit(event) {
    event.preventDefault();
    if (required && !String(value).trim()) return setError(`${fieldLabel} is required.`);
    setBusy(true);
    setError('');
    try {
      await onConfirm?.(value);
      onClose?.();
    } catch (err) {
      setError(err.message || 'Action failed.');
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="modal-card" style={{ maxWidth: 520 }}>
        <div className="modal-header">
          <div><h2 id={titleId}>{title}</h2>{!!description && <p className="muted">{description}</p>}</div>
          <button type="button" className="secondary" onClick={onClose} disabled={busy}>Close</button>
        </div>
        <form className="modal-form stack-tight" onSubmit={submit}>
          {showField && <label className="field">{fieldLabel}
            {inputType === 'textarea'
              ? <textarea value={value} onChange={(event) => setValue(event.target.value)} autoFocus />
              : <input type={inputType} min={min} max={max} value={value} onChange={(event) => setValue(event.target.value)} autoFocus />}
          </label>}
          {!!error && <p className="error-text">{error}</p>}
          <div className="row wrap">
            <button type="submit" className={tone === 'danger' ? 'danger' : 'primary'} disabled={busy}>{busy ? 'Processing...' : confirmLabel}</button>
            <button type="button" className="secondary" onClick={onClose} disabled={busy}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}
