const OFFLINE_DRAFTS_KEY = 'pos_offline_order_drafts_v1';

function readRawDrafts() {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(OFFLINE_DRAFTS_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeRawDrafts(rows) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(OFFLINE_DRAFTS_KEY, JSON.stringify(rows));
}

export function listOfflineDrafts() {
  return readRawDrafts().sort((a, b) => String(b.saved_at || '').localeCompare(String(a.saved_at || '')));
}

export function saveOfflineDraft(snapshot) {
  const now = new Date().toISOString();
  const draft = {
    id: snapshot?.id || `offline-${Date.now()}`,
    saved_at: now,
    status: 'local_only',
    ...snapshot,
  };
  const rows = listOfflineDrafts().filter((row) => row.id !== draft.id);
  writeRawDrafts([draft, ...rows].slice(0, 50));
  return draft;
}

export function removeOfflineDraft(id) {
  writeRawDrafts(listOfflineDrafts().filter((row) => row.id !== id));
}

export function clearOfflineDrafts() {
  writeRawDrafts([]);
}
