'use client';

import { useEffect, useState } from 'react';
import { fetchAccountingHealth, getSystemSettings, seedDefaults, updateSystemSettings } from '../../lib/api';

const PATH_FIELDS = [
  ['integration_token_path', 'Integration Token Path', '/auth/integration/token'],
  ['healthcheck_path', 'Accounting Health Path', '/healthz'],
  ['current_erp_sales_path', 'Sales Path', ''],
  ['current_erp_cashflow_path', 'Cashflow Path', ''],
  ['current_erp_reconciliation_path', 'Reconciliation Path', ''],
  ['current_erp_transfers_path', 'Transfers Path', ''],
  ['current_erp_financial_accounts_path', 'Financial Accounts Path', ''],
  ['current_erp_receivables_path', 'Receivables Path', ''],
  ['catalog_items_path', 'Catalog Items Path', ''],
  ['catalog_skus_path', 'Catalog SKUs Path', ''],
];

export default function SettingsPage() {
  const [settings, setSettings] = useState({ accounting_sync: {}, ui_preferences: {} });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [healthStatus, setHealthStatus] = useState('');
  const [healthError, setHealthError] = useState('');
  const [healthDetails, setHealthDetails] = useState(null);
  const [busy, setBusy] = useState('');

  async function loadSettings() {
    try {
      const data = await getSystemSettings();
      setSettings(data || { accounting_sync: {}, ui_preferences: {} });
    } catch (e) {
      setError(e.message || 'Failed to load settings.');
    }
  }

  useEffect(() => { loadSettings().catch(console.error); }, []);

  function setSyncField(key, value) {
    setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, [key]: value } }));
  }

  async function handleSave(event) {
    event.preventDefault();
    setError(''); setNotice(''); setBusy('save');
    try {
      await updateSystemSettings({ ...settings, accounting_sync: { ...(settings.accounting_sync || {}), mode: 'current_erp' } });
      setNotice('Settings saved. Stored secrets remain masked.');
      await loadSettings();
    } catch (e) {
      setError(e.message || 'Failed to save settings.');
    } finally {
      setBusy('');
    }
  }

  async function handleSeed() {
    setError(''); setNotice(''); setBusy('seed');
    try {
      await seedDefaults();
      setNotice('Default outlet, register, and sync settings ensured.');
      await loadSettings();
    } catch (e) {
      setError(e.message || 'Failed to seed defaults.');
    } finally {
      setBusy('');
    }
  }

  async function handleTestConnection() {
    setHealthStatus(''); setHealthError(''); setHealthDetails(null); setBusy('health');
    try {
      const data = await fetchAccountingHealth();
      const rows = Array.isArray(data?.rows) ? data.rows : [];
      const healthyCount = Number.isFinite(Number(data?.healthy_count)) ? Number(data.healthy_count) : rows.filter((row) => row.healthy).length;
      const totalCount = Number.isFinite(Number(data?.total_count)) ? Number(data.total_count) : rows.length;
      const failedRows = rows.filter((row) => !row.healthy);
      const checkedAt = new Date().toLocaleString();
      setHealthDetails({ ...data, rows, healthy_count: healthyCount, total_count: totalCount, failed_rows: failedRows, checked_at: checkedAt });
      const mappingText = totalCount ? `${healthyCount}/${totalCount} register mappings healthy` : 'no register mappings checked';
      const issueText = failedRows.length ? ` ${failedRows.length} mapping needs attention.` : ' All checked mappings are healthy.';
      setHealthStatus(`Accounting API reachable and token accepted: ${mappingText}.${issueText}`);
    } catch (e) {
      setHealthError(e.message || 'Accounting connection test failed.');
    } finally {
      setBusy('');
    }
  }

  const sync = settings.accounting_sync || {};

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Settings</h1>
            <p className="muted">Connect this POS to the Accounting ERP receiver.</p>
          </div>
          <div className="row wrap" style={{ gap: 10 }}>
            <button className="secondary" onClick={handleSeed} disabled={!!busy}>{busy === 'seed' ? 'Ensuring...' : 'Ensure defaults'}</button>
            <button className="secondary" onClick={handleTestConnection} disabled={!!busy}>{busy === 'health' ? 'Testing...' : 'Test accounting connection'}</button>
          </div>
        </div>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <h2>Accounting Sync</h2>
        {!!healthStatus && <p className="success-text" style={{ marginTop: 8 }}>{healthStatus}</p>}
        {!!healthError && <p className="error-text" style={{ marginTop: 8 }}>{healthError}</p>}
        {healthDetails && (
          <div className="card-grid" style={{ marginTop: 12 }}>
            <div className="card"><div className="muted">Last checked</div><strong>{healthDetails.checked_at}</strong></div>
            <div className="card"><div className="muted">Checked mappings</div><strong>{healthDetails.total_count}</strong></div>
            <div className="card"><div className="muted">Healthy mappings</div><strong>{healthDetails.healthy_count}</strong></div>
            <div className="card"><div className="muted">Needs attention</div><strong>{healthDetails.failed_rows.length}</strong></div>
            {!!healthDetails.failed_rows.length && (
              <div className="card wide">
                <strong>Missing or failed mappings</strong>
                <ul className="compact-list">
                  {healthDetails.failed_rows.map((row) => (
                    <li key={row.register_id || row.register_code}>
                      {row.register_name || row.register_code || `Register ${row.register_id}`} needs a valid Accounting financial account.
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        <p className="muted">Accounting owns menu items, categories, pricing, recipes, and SKUs. POS consumes that catalog for sales and keeps only operational availability overrides. Saved secrets are never displayed again.</p>
        <form className="form-grid" style={{ marginTop: 12 }} onSubmit={handleSave}>
          <label className="field">Mode<select value="current_erp" disabled><option value="current_erp">current_erp</option></select></label>
          <label className="field">Accounting API Base<input value={sync.api_base || ''} onChange={(e) => setSyncField('api_base', e.target.value)} placeholder="https://accounting.hiddenoasis.app/api" /></label>
          <label className="field">Integration Secret<input type="password" value={sync.integration_secret || ''} onChange={(e) => setSyncField('integration_secret', e.target.value)} placeholder={sync.integration_secret_configured ? 'Saved - enter a new secret only to replace it' : 'Enter integration secret'} /></label>

          <details className="advanced-settings">
            <summary>Advanced connection paths</summary>
            <p className="small muted" style={{ marginTop: 8 }}>Leave these at their defaults unless the Accounting API routes have changed.</p>
            <div className="form-grid" style={{ marginTop: 12 }}>
              <label className="field">Accounting API Token<input type="password" value={sync.api_token || ''} onChange={(e) => setSyncField('api_token', e.target.value)} placeholder={sync.api_token_configured ? 'Saved - enter a new token only to replace it' : 'Optional fallback token'} /></label>
              {PATH_FIELDS.map(([key, label, placeholder]) => (
                <label className="field" key={key}>{label}<input value={sync[key] || ''} onChange={(e) => setSyncField(key, e.target.value)} placeholder={placeholder} /></label>
              ))}
            </div>
          </details>

          <div className="row wrap"><button type="submit" className="primary" disabled={!!busy}>{busy === 'save' ? 'Saving...' : 'Save Settings'}</button></div>
        </form>
      </section>
    </div>
  );
}
