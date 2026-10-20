const OFFLINE_DRAFTS_KEY = 'pos_offline_order_drafts_v2';
const LEGACY_OFFLINE_DRAFTS_KEY = 'pos_offline_order_drafts_v1';
const SCHEMA_VERSION = 2;
const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000;

function readRawDrafts() {
  if (typeof window === 'undefined') return [];
  const readList = (key) => {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(key) || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      // A damaged legacy key must not hide a valid current recovery draft.
      try { window.localStorage.removeItem(key); } catch { /* unavailable storage */ }
      return [];
    }
  };
  const current = readList(OFFLINE_DRAFTS_KEY);
  const legacy = readList(LEGACY_OFFLINE_DRAFTS_KEY);
  try { window.localStorage.removeItem(LEGACY_OFFLINE_DRAFTS_KEY); } catch { /* unavailable storage */ }
  return [...current, ...legacy];
}

function writeRawDrafts(rows) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(OFFLINE_DRAFTS_KEY, JSON.stringify(rows));
}

function activeRows(rows) {
  const now = Date.now();
  return rows.flatMap((row) => {
    if (!row || typeof row !== 'object' || Array.isArray(row) || !row.id) return [];
    const savedAt = Date.parse(row.saved_at || '');
    const explicitExpiry = Date.parse(row.expires_at || '');
    // Legacy records without expires_at get 24h from their saved_at. Records
    // with neither timestamp are discarded rather than retained forever.
    const expiry = Number.isFinite(explicitExpiry)
      ? explicitExpiry
      : Number.isFinite(savedAt) ? savedAt + DEFAULT_TTL_MS : NaN;
    if (!Number.isFinite(expiry) || expiry <= now) return [];
    return [{ ...row, expires_at: new Date(expiry).toISOString() }];
  });
}

export function listOfflineDrafts({ ownerId = null, registerId = null } = {}) {
  const rows = activeRows(readRawDrafts())
    .map((row) => ({
      ...row,
      ownership_mismatch: Boolean(
        (ownerId != null && row.owner_id != null && String(ownerId) !== String(row.owner_id))
        || (registerId != null && row.register_id != null && String(registerId) !== String(row.register_id))
      ),
    }))
    .sort((a, b) => String(b.saved_at || '').localeCompare(String(a.saved_at || '')));
  writeRawDrafts(rows.map(({ ownership_mismatch, ...row }) => row));
  return rows;
}

export function saveOfflineDraft(snapshot, { ownerId = null, ownerLabel = '', registerId = null, ttlMs = DEFAULT_TTL_MS } = {}) {
  const now = new Date().toISOString();
  const draft = {
    ...snapshot,
    schema_version: SCHEMA_VERSION,
    id: snapshot?.id || (typeof crypto !== 'undefined' && crypto.randomUUID ? `offline-${crypto.randomUUID()}` : `offline-${Date.now()}`),
    saved_at: now,
    expires_at: new Date(Date.now() + Math.max(60_000, Number(ttlMs) || DEFAULT_TTL_MS)).toISOString(),
    status: 'local_only',
    owner_id: ownerId,
    owner_label: String(ownerLabel || '').slice(0, 80),
    register_id: registerId,
  };
  const rows = listOfflineDrafts().filter((row) => row.id !== draft.id).map(({ ownership_mismatch, ...row }) => row);
  writeRawDrafts([draft, ...rows].slice(0, 50));
  return draft;
}

export function removeOfflineDraft(id) {
  writeRawDrafts(listOfflineDrafts().filter((row) => row.id !== id));
}

export function clearOfflineDrafts() {
  writeRawDrafts([]);
}
