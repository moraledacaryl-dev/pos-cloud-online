'use client';

import { useEffect, useMemo, useState } from 'react';
import ActionModal from '../../components/ActionModal';
import { deleteRecipePdf, fetchRecipeDishes, fetchRecipePdf, uploadRecipePdf } from '../../lib/api';
import { filterRecipeDishes, validateRecipePdfFile } from '../../lib/recipeLibrary.mjs';
import { useCurrentUser } from '../../lib/useCurrentUser';

function fileSize(value) {
  const bytes = Number(value || 0);
  if (!bytes) return '-';
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function updatedAt(value) {
  if (!value) return '-';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export default function RecipesPage() {
  const { can } = useCurrentUser();
  const canManage = can('recipes.manage');
  const [dishes, setDishes] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('all');
  const [status, setStatus] = useState('all');
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [readerUrl, setReaderUrl] = useState('');
  const [readerTitle, setReaderTitle] = useState('');
  const [pendingDelete, setPendingDelete] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function loadDishes() {
    try {
      const rows = await fetchRecipeDishes();
      const nextRows = Array.isArray(rows) ? rows : [];
      setDishes(nextRows);
      setSelectedId((current) => nextRows.some((row) => row.external_menu_item_id === current) ? current : nextRows[0]?.external_menu_item_id || null);
    } catch (e) {
      setError(e.message || 'Failed to load recipe dishes.');
    }
  }

  useEffect(() => { loadDishes().catch(console.error); }, []);
  useEffect(() => () => { if (readerUrl) URL.revokeObjectURL(readerUrl); }, [readerUrl]);

  const categories = useMemo(() => Array.from(new Set(dishes.map((row) => row.category_name || 'Uncategorized'))).sort(), [dishes]);
  const visibleDishes = useMemo(() => filterRecipeDishes(dishes, { q, category, status }), [dishes, q, category, status]);
  const selected = useMemo(() => dishes.find((row) => row.external_menu_item_id === selectedId) || null, [dishes, selectedId]);
  const withPdfCount = useMemo(() => dishes.filter((row) => !!row.recipe).length, [dishes]);

  useEffect(() => {
    setTitle(selected?.recipe?.title || selected?.dish_name || '');
    setNotes(selected?.recipe?.notes || '');
    setFile(null);
    setFileInputKey((value) => value + 1);
  }, [selectedId, selected?.recipe?.updated_at]);

  async function openReader() {
    if (!selected?.recipe) return;
    setError('');
    setBusy(true);
    try {
      const blob = await fetchRecipePdf(selected.external_menu_item_id);
      setReaderUrl(URL.createObjectURL(blob));
      setReaderTitle(selected.recipe.title || selected.dish_name);
    } catch (e) {
      setError(e.message || 'Failed to open recipe PDF.');
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(event) {
    event.preventDefault();
    if (!selected) return;
    setError(''); setNotice('');
    const validationError = validateRecipePdfFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusy(true);
    try {
      await uploadRecipePdf({ menuItemId: selected.external_menu_item_id, file, title, notes });
      setNotice(`${selected.dish_name} recipe PDF ${selected.recipe ? 'replaced' : 'uploaded'}.`);
      setFile(null);
      setFileInputKey((value) => value + 1);
      await loadDishes();
    } catch (e) {
      setError(e.message || 'Failed to upload recipe PDF.');
    } finally {
      setBusy(false);
    }
  }

  async function removePdf() {
    if (!pendingDelete) return;
    try {
      await deleteRecipePdf(pendingDelete.external_menu_item_id);
      setNotice(`${pendingDelete.dish_name} recipe PDF removed.`);
      setPendingDelete(null);
      if (readerUrl) setReaderUrl('');
      await loadDishes();
    } catch (e) {
      setError(e.message || 'Failed to remove recipe PDF.');
      throw e;
    }
  }

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Recipe Library</h1>
            <p className="muted">Staff recipe PDFs for dishes synced from the Accounting menu.</p>
            <p className="small muted" style={{ marginTop: 4 }}>Accounting remains the menu master. Each dish can have one current POS recipe PDF, shared across its variants.</p>
          </div>
          <div className="row wrap">
            <span className="badge info">{dishes.length} Accounting dishes</span>
            <span className="badge success">{withPdfCount} with PDF</span>
            <span className="badge warn">{dishes.length - withPdfCount} missing PDF</span>
          </div>
        </div>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <div className="recipe-filter-grid">
          <label className="field">Search dishes<input placeholder="Dish, category, or variant" value={q} onChange={(e) => setQ(e.target.value)} /></label>
          <label className="field">Category<select value={category} onChange={(e) => setCategory(e.target.value)}><option value="all">All categories</option>{categories.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
          <label className="field">PDF status<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">All dishes</option><option value="with_pdf">With PDF</option><option value="missing_pdf">Missing PDF</option></select></label>
        </div>
      </section>

      <div className="recipe-library-layout">
        <section className="section recipe-dish-list">
          <div><h2>Accounting Dishes</h2><p className="small muted">{visibleDishes.length} matching dishes</p></div>
          <div className="recipe-dish-grid">
            {visibleDishes.map((row) => <button type="button" key={row.external_menu_item_id} className={`recipe-dish-card ${selectedId === row.external_menu_item_id ? 'selected' : ''}`} onClick={() => setSelectedId(row.external_menu_item_id)}>
              <span><strong>{row.dish_name}</strong><small>{row.category_name || 'Uncategorized'} / {row.variant_count} {row.variant_count === 1 ? 'variant' : 'variants'}</small></span>
              <span className={`badge ${row.recipe ? 'success' : 'warn'}`}>{row.recipe ? 'PDF ready' : 'Missing'}</span>
            </button>)}
            {!visibleDishes.length && <p className="muted">No Accounting dishes match this filter.</p>}
          </div>
        </section>

        <section className="section">
          {!selected && <p className="muted">Select a dish to view its recipe.</p>}
          {selected && <>
            <div className="toolbar">
              <div><h2>{selected.dish_name}</h2><p className="small muted">{selected.category_name || 'Uncategorized'} / Accounting menu item #{selected.external_menu_item_id}</p></div>
              <span className={`badge ${selected.recipe ? 'success' : 'warn'}`}>{selected.recipe ? 'PDF available' : 'No PDF yet'}</span>
            </div>
            {selected.recipe ? <div className="recipe-document-summary">
              <div><span>Document</span><strong>{selected.recipe.title}</strong></div>
              <div><span>File</span><strong>{selected.recipe.original_filename} / {fileSize(selected.recipe.file_size)}</strong></div>
              <div><span>Updated</span><strong>{updatedAt(selected.recipe.updated_at)}</strong></div>
              <div><span>Uploaded by</span><strong>{selected.recipe.uploaded_by_name || 'POS manager'}</strong></div>
              {!!selected.recipe.notes && <div><span>Notes</span><strong>{selected.recipe.notes}</strong></div>}
              <div className="row wrap">
                <button type="button" className="primary" onClick={openReader} disabled={busy}>{busy ? 'Opening...' : 'Open PDF Reader'}</button>
                {canManage && <button type="button" className="danger" onClick={() => setPendingDelete(selected)}>Remove PDF</button>}
              </div>
            </div> : <p className="muted" style={{ marginTop: 12 }}>No recipe has been uploaded for this dish yet.</p>}

            {canManage && <form className="recipe-upload-panel" onSubmit={handleUpload}>
              <div><h3>{selected.recipe ? 'Replace recipe PDF' : 'Upload recipe PDF'}</h3><p className="small muted">PDF only, up to 15 MB. Uploading again replaces the prior file for this dish.</p></div>
              <label className="field">Recipe title<input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={selected.dish_name} /></label>
              <label className="field">Notes<textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional staff guidance" rows={3} /></label>
              <label className="field">PDF file<input key={fileInputKey} type="file" accept=".pdf,application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
              <button type="submit" className="primary" disabled={busy}>{busy ? 'Uploading...' : selected.recipe ? 'Replace PDF' : 'Upload PDF'}</button>
            </form>}
          </>}
        </section>
      </div>

      {!!readerUrl && <section className="section recipe-reader-section">
        <div className="toolbar">
          <div><h2>{readerTitle}</h2><p className="small muted">Staff PDF reader</p></div>
          <div className="row wrap"><a className="button-link secondary-link" href={readerUrl} target="_blank" rel="noreferrer">Open in New Tab</a><button type="button" className="secondary" onClick={() => setReaderUrl('')}>Close Reader</button></div>
        </div>
        <iframe className="recipe-pdf-reader" src={readerUrl} title={`${readerTitle} PDF`} />
      </section>}

      <ActionModal
        open={!!pendingDelete}
        title={`Remove ${pendingDelete?.dish_name || 'recipe'} PDF?`}
        description="Staff will no longer be able to open this recipe until a new PDF is uploaded."
        showField={false}
        confirmLabel="Remove PDF"
        onClose={() => setPendingDelete(null)}
        onConfirm={removePdf}
      />
    </div>
  );
}
