'use client';

import { useEffect, useMemo, useState } from 'react';
import { createCatalogItem, deleteCatalogItem, fetchCatalogItems, request, syncCatalogFromAccounting, updateCatalogItem } from '../../lib/api';
import ActionModal from '../../components/ActionModal';

function money(value) {
  return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatSyncAge(status) {
  if (!status?.last_sync_at) return 'Never synchronized';
  if (status.age_minutes < 60) return `${status.age_minutes} minute${status.age_minutes === 1 ? '' : 's'} ago`;
  const hours = Math.floor(status.age_minutes / 60);
  return `${hours} hour${hours === 1 ? '' : 's'} ago`;
}

const blank = { id: null, menu_item_name: '', display_name: '', sku_code: '', variant_name: '', category_name: '', module_slug: 'restaurant', prep_station: 'kitchen', price: '0', is_active: true, is_available: true, notes: '' };

export default function CatalogPage() {
  const [items, setItems] = useState([]);
  const [catalogStatus, setCatalogStatus] = useState(null);
  const [q, setQ] = useState('');
  const [availabilityFilter, setAvailabilityFilter] = useState('all');
  const [form, setForm] = useState(blank);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showLocalEditor, setShowLocalEditor] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  async function loadItems() {
    try {
      const [rows, status] = await Promise.all([
        fetchCatalogItems({ q }),
        request('/catalog/status'),
      ]);
      setItems(Array.isArray(rows) ? rows : []);
      setCatalogStatus(status || null);
    } catch (e) { setError(e.message || 'Failed to load catalog.'); }
  }

  useEffect(() => { loadItems().catch(console.error); }, [q]);
  const visibleItems = useMemo(() => items.filter((row) => availabilityFilter === 'all' || (availabilityFilter === 'available' ? row.is_available : !row.is_available)), [items, availabilityFilter]);
  const grouped = useMemo(() => visibleItems.reduce((acc, row) => { const key = row.category_name || 'Uncategorized'; acc[key] = acc[key] || []; acc[key].push(row); return acc; }, {}), [visibleItems]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(''); setNotice('');
    setBusy(true);
    try {
      const payload = { ...form, price: Number(form.price || 0) };
      if (form.id) await updateCatalogItem(form.id, payload);
      else await createCatalogItem(payload);
      setNotice(`Catalog fallback ${form.id ? 'updated' : 'saved'}.`);
      setForm(blank);
      await loadItems();
    } catch (e) { setError(e.message || 'Failed to save catalog fallback.'); }
    finally { setBusy(false); }
  }

  async function handleSync() {
    setError(''); setNotice('');
    setBusy(true);
    try {
      const res = await syncCatalogFromAccounting();
      setNotice(`Refreshed ${res.imported_rows} POS selling rows through the Accounting compatibility API. Inventory remains the catalog business owner.`);
      await loadItems();
    } catch (e) { setError(e.message || 'Failed to refresh the selling catalog.'); }
    finally { setBusy(false); }
  }

  function editItem(row) {
    setForm({ ...row, id: row.id, price: String(row.price || 0), notes: row.notes || '' });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function toggleAvailability(row) {
    updateCatalogItem(row.id, { is_available: !row.is_available }).then(() => {
      setNotice(`${row.display_name || row.menu_item_name} is now ${row.is_available ? 'sold out / hidden from POS' : 'available in POS'}.`);
      loadItems();
    }).catch((e) => setError(e.message || 'Failed to update availability.'));
  }

  async function deleteFallbackItem() {
    if (!pendingDelete) return;
    try {
      await deleteCatalogItem(pendingDelete.id);
      setNotice(`Deleted local-only fallback ${pendingDelete.display_name || pendingDelete.menu_item_name}.`);
      await loadItems();
    } catch (e) {
      setError(e.message || 'Failed to delete catalog fallback.');
      throw e;
    }
  }

  const statusClass = catalogStatus?.state === 'fresh' ? 'success' : 'warn';

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Catalog</h1>
            <p className="muted">POS selling snapshot with local sold-out controls.</p>
            <p className="small muted" style={{ marginTop: 4 }}>Inventory & Procurement owns product identity, SKUs, recipes, stock, and master availability. Accounting currently transports the compatible menu feed. POS stores a selling snapshot and may only apply local availability overrides.</p>
            <div className="row wrap" style={{ marginTop: 8 }}>
              <span className={`badge ${statusClass}`}>{catalogStatus?.state === 'fresh' ? 'Catalog fresh' : catalogStatus?.state === 'stale' ? 'Catalog stale' : 'Catalog not synced'}</span>
              <span className="small muted">Last refresh: {formatSyncAge(catalogStatus)}</span>
              {!!catalogStatus?.imported_rows && <span className="small muted">{catalogStatus.imported_rows} selling rows</span>}
            </div>
          </div>
          <div className="row wrap">
            <button className="primary" onClick={handleSync} disabled={busy}>{busy ? 'Working...' : 'Refresh Selling Catalog'}</button>
            <select value={availabilityFilter} onChange={(e) => setAvailabilityFilter(e.target.value)}>
              <option value="all">All items</option>
              <option value="available">Available only</option>
              <option value="sold_out">Sold out / hidden</option>
            </select>
            <input placeholder="Search catalog" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 220 }} />
          </div>
        </div>
        {catalogStatus?.state === 'stale' && <p className="error-text" style={{ marginTop: 8 }}>The selling snapshot is more than 24 hours old. Refresh before relying on prices or item availability.</p>}
        {catalogStatus?.state === 'never_synced' && <p className="error-text" style={{ marginTop: 8 }}>This POS has not completed a catalog refresh. Do not treat local fallback items as master products.</p>}
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <div className="toolbar">
          <div><h2>Local-only fallback items</h2><p className="small muted">Emergency use only. Create the permanent product in Inventory, then refresh the POS catalog and retire the fallback.</p></div>
          <button type="button" className="secondary" onClick={() => setShowLocalEditor((open) => !open)}>{showLocalEditor ? 'Hide fallback editor' : 'Add local-only fallback'}</button>
        </div>
        {(showLocalEditor || form.id) && <>
        <h3 style={{ marginTop: 14 }}>{form.id ? 'Edit Local-only Item' : 'New Local-only Item'}</h3>
        <form className="form-grid-3" style={{ marginTop: 12 }} onSubmit={handleSubmit}>
          <label className="field">Menu Item Name<input value={form.menu_item_name} onChange={(e) => setForm((prev) => ({ ...prev, menu_item_name: e.target.value }))} /></label>
          <label className="field">Display Name<input value={form.display_name} onChange={(e) => setForm((prev) => ({ ...prev, display_name: e.target.value }))} /></label>
          <label className="field">SKU Code<input value={form.sku_code} onChange={(e) => setForm((prev) => ({ ...prev, sku_code: e.target.value }))} /></label>
          <label className="field">Variant name<input value={form.variant_name} onChange={(e) => setForm((prev) => ({ ...prev, variant_name: e.target.value }))} /></label>
          <label className="field">Category<input value={form.category_name} onChange={(e) => setForm((prev) => ({ ...prev, category_name: e.target.value }))} /></label>
          <label className="field">Module<input value={form.module_slug} onChange={(e) => setForm((prev) => ({ ...prev, module_slug: e.target.value }))} /></label>
          <label className="field">Prep Station<input value={form.prep_station} onChange={(e) => setForm((prev) => ({ ...prev, prep_station: e.target.value }))} /></label>
          <label className="field">Price<input type="number" step="0.01" value={form.price} onChange={(e) => setForm((prev) => ({ ...prev, price: e.target.value }))} /></label>
          <label className="field">Available<select value={String(!!form.is_available)} onChange={(e) => setForm((prev) => ({ ...prev, is_available: e.target.value === 'true' }))}><option value="true">Yes</option><option value="false">No</option></select></label>
          <label className="field" style={{ gridColumn: '1 / -1' }}>Notes<input value={form.notes} onChange={(e) => setForm((prev) => ({ ...prev, notes: e.target.value }))} /></label>
          <div className="row wrap"><button type="submit" className="primary" disabled={busy}>{busy ? 'Saving...' : form.id ? 'Update Item' : 'Save Local-only Item'}</button>{form.id && <button type="button" className="secondary" onClick={() => setForm(blank)}>Cancel Edit</button>}</div>
        </form>
        </>}
      </section>

      {Object.entries(grouped).map(([group, rows]) => (
        <section className="section" key={group}>
          <h2>{group}</h2>
          <table className="table" style={{ marginTop: 10 }}>
            <thead><tr><th>Display</th><th>SKU / Variant</th><th>Station</th><th>Price</th><th>Master IDs</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}><td>{row.display_name}</td><td>{row.sku_code || '-'}</td><td>{row.prep_station || '-'}</td><td>{money(row.price)}</td><td>{row.external_menu_item_id || '-'} / {row.external_sku_id || '-'}</td><td><span className={`badge ${row.is_available ? 'success' : 'warn'}`}>{row.is_available ? 'available' : 'sold out'}</span></td><td><div className="row wrap">{!row.external_menu_item_id && !row.external_sku_id && <button type="button" className="secondary" onClick={() => editItem(row)}>Edit fallback</button>}<button type="button" className={row.is_available ? 'secondary' : 'primary'} onClick={() => toggleAvailability(row)}>{row.is_available ? 'Mark Sold Out' : 'Restore to POS'}</button>{!row.external_menu_item_id && !row.external_sku_id && <button type="button" className="danger" onClick={() => setPendingDelete(row)}>Delete fallback</button>}</div></td></tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
      {!visibleItems.length && <section className="section"><p className="muted">No catalog items match this filter.</p></section>}
      <ActionModal
        open={!!pendingDelete}
        title={`Delete ${pendingDelete?.display_name || pendingDelete?.menu_item_name || 'local-only item'}?`}
        description="This deletes only the POS fallback item. Master-managed products cannot be deleted here."
        showField={false}
        confirmLabel="Delete fallback"
        onClose={() => setPendingDelete(null)}
        onConfirm={deleteFallbackItem}
      />
    </div>
  );
}