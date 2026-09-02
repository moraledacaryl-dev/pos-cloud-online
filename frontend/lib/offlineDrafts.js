const OFFLINE_DRAFTS_KEY = 'pos_offline_order_drafts_v2';
const LEGACY_OFFLINE_DRAFTS_KEY = 'pos_offline_order_drafts_v1';
const SCHEMA_VERSION = 2;
const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000;

function readRawDrafts() {
  if (typeof window === 'undefined') return [];
  try {
    const current = JSON.parse(window.localStorage.getItem(OFFLINE_DRAFTS_KEY) || '[]');
    const legacy = JSON.parse(window.localStorage.getItem(LEGACY_OFFLINE_DRAFTS_KEY) || '[]');
    const rows = [...(Array.isArray(current) ? current : []), ...(Array.isArray(legacy) ? legacy : [])];
    window.localStorage.removeItem(LEGACY_OFFLINE_DRAFTS_KEY);
    return rows;
  } catch {
    return [];
  }
}

function writeRawDrafts(rows) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(OFFLINE_DRAFTS_KEY, JSON.stringify(rows));
}

function activeRows(rows) {
  const now = Date.now();
  return rows.filter((row) => {
    const expiry = Date.parse(row.expires_at || '');
    return !Number.isFinite(expiry) || expiry > now;
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
