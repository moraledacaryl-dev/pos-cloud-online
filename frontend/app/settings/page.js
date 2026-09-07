'use client';

import { useEffect, useMemo, useState } from 'react';
import { fetchAccountingHealth, getSystemSettings, seedDefaults, updateSystemSettings } from '../../lib/api';
import ActionModal from '../../components/ActionModal';

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
  const [settings, setSettings] = useState({ accounting_sync: {}, ui_preferences: {}, receipt_profile: {} });
  const [savedSettings, setSavedSettings] = useState({ accounting_sync: {}, ui_preferences: {}, receipt_profile: {} });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [healthStatus, setHealthStatus] = useState('');
  const [healthError, setHealthError] = useState('');
  const [healthDetails, setHealthDetails] = useState(null);
  const [busy, setBusy] = useState('');
  const [confirmDefaults, setConfirmDefaults] = useState(false);

  async function loadSettings() {
    try {
      const data = await getSystemSettings();
      const next = data || { accounting_sync: {}, ui_preferences: {}, receipt_profile: {} };
      setSettings(next);
      setSavedSettings(next);
    } catch (e) {
      setError(e.message || 'Failed to load settings.');
    }
  }

  useEffect(() => { loadSettings().catch(console.error); }, []);

  function setSyncField(key, value) {
    setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, [key]: value } }));
  }

  function setReceiptField(key, value) {
    setSettings((prev) => ({ ...prev, receipt_profile: { ...prev.receipt_profile, [key]: value } }));
  }

  async function handleSave(event) {
    event.preventDefault();
    setError(''); setNotice(''); setBusy('save');
    try {
      const base = String(settings.accounting_sync?.api_base || '').trim();
      if (!base) throw new Error('Enter the Accounting API base URL.');
      const parsed = new URL(base);
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('Accounting API URL must use http or https.');
      for (const [key, label] of PATH_FIELDS) {
        const value = String(settings.accounting_sync?.[key] || '').trim();
        if (value && !value.startsWith('/')) throw new Error(`${label} must start with /.`);
      }
      const receipt = settings.receipt_profile || {};
      if ((receipt.registration_status || 'unregistered') === 'registered') {
        const required = [
          ['tax_registration_type', 'Tax registration type'],
          ['registered_name', 'Registered name'],
          ['business_address', 'Business address'],
          ['tin', 'TIN'],
          ['branch_code', 'Branch code'],
          ['machine_identification_number', 'Machine identification number'],
          ['serial_number', 'POS serial number'],
          ['permit_to_use_number', 'Permit to use number'],
        ];
        const missing = required.filter(([key]) => !String(receipt[key] || '').trim()).map(([, label]) => label);
        if (missing.length) throw new Error(`Complete the registered invoice profile: ${missing.join(', ')}.`);
      }
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
  const receipt = settings.receipt_profile || {};
  const dirty = useMemo(() => JSON.stringify(settings) !== JSON.stringify(savedSettings), [settings, savedSettings]);

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Settings</h1>
            <p className="muted">Connect this POS to the Accounting ERP receiver.</p>
          </div>
          <div className="row wrap" style={{ gap: 10 }}>
            <button className="secondary" onClick={() => setConfirmDefaults(true)} disabled={!!busy}>{busy === 'seed' ? 'Creating...' : 'Create missing POS defaults'}</button>
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
          <label className="field">Accounting Connector<select value="current_erp" disabled><option value="current_erp">Hidden Oasis Accounting</option></select></label>
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

          <div className="settings-subsection wide">
            <div>
              <h2>Sales Invoice & BIR Registration</h2>
              <p className="muted">Configure the exact registered details issued for this POS terminal. Keep this set to Unregistered until the BIR permit, machine identification number, and serial details are verified.</p>
            </div>
            <div className="form-grid" style={{ marginTop: 12 }}>
              <label className="field">Registration Status<select value={receipt.registration_status || 'unregistered'} onChange={(e) => setReceiptField('registration_status', e.target.value)}><option value="unregistered">Unregistered / training output</option><option value="registered">Registered for official invoices</option></select></label>
              <label className="field">Tax Registration<select value={receipt.tax_registration_type || ''} onChange={(e) => setReceiptField('tax_registration_type', e.target.value)}><option value="">Select tax registration</option><option value="vat">VAT Registered</option><option value="non_vat">Non-VAT</option></select></label>
              <label className="field">Registered Business Name<input value={receipt.registered_name || ''} onChange={(e) => setReceiptField('registered_name', e.target.value)} /></label>
              <label className="field">Trade Name<input value={receipt.trade_name || ''} onChange={(e) => setReceiptField('trade_name', e.target.value)} /></label>
              <label className="field wide">Registered Business Address<input value={receipt.business_address || ''} onChange={(e) => setReceiptField('business_address', e.target.value)} /></label>
              <label className="field">TIN<input value={receipt.tin || ''} onChange={(e) => setReceiptField('tin', e.target.value)} inputMode="numeric" /></label>
              <label className="field">Branch Code<input value={receipt.branch_code || ''} onChange={(e) => setReceiptField('branch_code', e.target.value)} /></label>
              <label className="field">Machine Identification Number<input value={receipt.machine_identification_number || ''} onChange={(e) => setReceiptField('machine_identification_number', e.target.value)} /></label>
              <label className="field">POS Serial Number<input value={receipt.serial_number || ''} onChange={(e) => setReceiptField('serial_number', e.target.value)} /></label>
              <label className="field">Permit to Use Number<input value={receipt.permit_to_use_number || ''} onChange={(e) => setReceiptField('permit_to_use_number', e.target.value)} /></label>
              <label className="field">Permit Date<input type="date" value={receipt.permit_date || ''} onChange={(e) => setReceiptField('permit_date', e.target.value)} /></label>
              <label className="field">Accreditation Number<input value={receipt.accreditation_number || ''} onChange={(e) => setReceiptField('accreditation_number', e.target.value)} /></label>
              <label className="field">Accreditation Date<input type="date" value={receipt.accreditation_date || ''} onChange={(e) => setReceiptField('accreditation_date', e.target.value)} /></label>
              <label className="field wide">Invoice Footer<input value={receipt.footer_message || ''} onChange={(e) => setReceiptField('footer_message', e.target.value)} placeholder="Thank you for visiting Hidden Oasis." /></label>
            </div>
            <p className={`small ${receipt.registration_status === 'registered' ? 'success-text' : 'notice-text'}`} style={{ marginTop: 10 }}>{receipt.registration_status === 'registered' ? 'Official Sales Invoice mode will be used after all fields are saved.' : 'Printed documents are visibly marked as provisional and not valid for tax claims.'}</p>
          </div>

          <div className="settings-save-bar"><span className={`small ${dirty ? 'notice-text' : 'muted'}`}>{dirty ? 'Unsaved changes' : 'All changes saved'}</span><div className="row wrap">{dirty && <button type="button" className="secondary" onClick={() => setSettings(savedSettings)}>Discard changes</button>}<button type="submit" className="primary" disabled={!!busy || !dirty}>{busy === 'save' ? 'Saving...' : 'Save Settings'}</button></div></div>
        </form>
      </section>
      <ActionModal
        open={confirmDefaults}
        title="Create missing POS defaults?"
        description="This creates only missing default outlet, register, and synchronization settings. Existing records are preserved. Review Registers afterward before opening a session."
        showField={false}
        confirmLabel="Create missing defaults"
        onClose={() => setConfirmDefaults(false)}
        onConfirm={async () => { await handleSeed(); setConfirmDefaults(false); }}
      />
    </div>
  );
}
