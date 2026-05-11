'use client';

import { useEffect, useState } from 'react';
import { getSystemSettings, seedDefaults, updateSystemSettings, fetchAccountingHealth } from '../../lib/api';

export default function SettingsPage() {
  const [settings, setSettings] = useState({ accounting_sync: {}, ui_preferences: {} });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [healthStatus, setHealthStatus] = useState('');
  const [healthError, setHealthError] = useState('');

  async function loadSettings() {
    try {
      const data = await getSystemSettings();
      setSettings(data || { accounting_sync: {}, ui_preferences: {} });
    } catch (e) { setError(e.message || 'Failed to load settings.'); }
  }

  useEffect(() => { loadSettings().catch(console.error); }, []);

  async function handleSave(event) {
    event.preventDefault();
    setError(''); setNotice('');
    try {
      await updateSystemSettings(settings);
      setNotice('Settings saved.');
      await loadSettings();
    } catch (e) { setError(e.message || 'Failed to save settings.'); }
  }

  async function handleSeed() {
    setError(''); setNotice('');
    try {
      await seedDefaults();
      setNotice('Default outlet, register, and sync settings ensured.');
      await loadSettings();
    } catch (e) { setError(e.message || 'Failed to seed defaults.'); }
  }

  async function handleTestConnection() {
    setHealthStatus('');
    setHealthError('');
    try {
      const data = await fetchAccountingHealth();
      const visibleAccounts = Number.isFinite(Number(data.financial_account_count)) ? `${data.financial_account_count} accounts visible` : 'account count not reported';
      setHealthStatus(`Accounting connection OK: ${visibleAccounts}.`);
    } catch (e) {
      setHealthError(e.message || 'Accounting connection test failed.');
    }
  }

  const sync = settings.accounting_sync || {};

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Settings</h1>
            <p className="muted">Use current ERP mode now, and shift to integration facade mode later without changing your POS operations.</p>
          </div>
          <div className="row wrap" style={{ gap: 10 }}>
            <button className="secondary" onClick={handleSeed}>Ensure defaults</button>
            <button className="secondary" onClick={handleTestConnection}>Test accounting connection</button>
          </div>
        </div>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <h2>Accounting Sync</h2>
        {!!healthStatus && <p className="success-text" style={{ marginTop: 8 }}>{healthStatus}</p>}
        {!!healthError && <p className="error-text" style={{ marginTop: 8 }}>{healthError}</p>}
        <p className="muted">Set the accounting backend base to the live Accounting API, e.g. <code>https://hiddenoasis.app/api</code>. Use the integration secret so POS can renew the accounting token automatically. Menu items, categories and master catalog structure are owned by accounting; POS consumes them for sales and local payments.</p>
        <form className="form-grid" style={{ marginTop: 12 }} onSubmit={handleSave}>
          <label className="field">Mode<select value={sync.mode || 'current_erp'} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, mode: e.target.value } }))}><option value="current_erp">current_erp</option><option value="future_facade">future_facade</option></select></label>
          <label className="field">Accounting API Base<input value={sync.api_base || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, api_base: e.target.value } }))} /></label>
          <label className="field">Accounting API Token<input value={sync.api_token || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, api_token: e.target.value } }))} /></label>
          <label className="field">Integration Secret<input type="password" value={sync.integration_secret || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, integration_secret: e.target.value } }))} /></label>
          <label className="field">Integration Token Path<input value={sync.integration_token_path || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, integration_token_path: e.target.value } }))} placeholder="/auth/integration/token" /></label>
          <label className="field">Sales Path<input value={sync.current_erp_sales_path || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, current_erp_sales_path: e.target.value } }))} /></label>
          <label className="field">Cashflow Path<input value={sync.current_erp_cashflow_path || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, current_erp_cashflow_path: e.target.value } }))} /></label>
          <label className="field">Reconciliation Path<input value={sync.current_erp_reconciliation_path || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, current_erp_reconciliation_path: e.target.value } }))} /></label>
          <label className="field">Transfers Path<input value={sync.current_erp_transfers_path || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, current_erp_transfers_path: e.target.value } }))} /></label>
          <label className="field">Financial Accounts Path<input value={sync.current_erp_financial_accounts_path || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, current_erp_financial_accounts_path: e.target.value } }))} /></label>
          <label className="field">Receivables Path<input value={sync.current_erp_receivables_path || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, current_erp_receivables_path: e.target.value } }))} /></label>
          <label className="field">Catalog Items Path<input value={sync.catalog_items_path || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, catalog_items_path: e.target.value } }))} /></label>
          <label className="field">Catalog SKUs Path<input value={sync.catalog_skus_path || ''} onChange={(e) => setSettings((prev) => ({ ...prev, accounting_sync: { ...prev.accounting_sync, catalog_skus_path: e.target.value } }))} /></label>
          <div className="row wrap"><button type="submit" className="primary">Save Settings</button></div>
        </form>
      </section>
    </div>
  );
}
