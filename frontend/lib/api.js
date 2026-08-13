import { createInFlightMutationRegistry, mutationRequestKey } from './requestGuards.mjs';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || '/api').replace(/\/+$/, '');
const mutationRegistry = createInFlightMutationRegistry();
let refreshPromise = null;

function readCookie(name) {
  if (typeof document === 'undefined') return '';
  const prefix = `${encodeURIComponent(name)}=`;
  const row = document.cookie.split(';').map((value) => value.trim()).find((value) => value.startsWith(prefix));
  return row ? decodeURIComponent(row.slice(prefix.length)) : '';
}

function qs(params = {}, multi = false) {
  const pairs = Object.entries(params).flatMap(([k, v]) => Array.isArray(v) && multi ? v.map((item) => [k, item]) : [[k, v]]);
  const filtered = pairs.filter(([, v]) => v !== '' && v !== null && typeof v !== 'undefined');
  return filtered.length ? `?${new URLSearchParams(filtered).toString()}` : '';
}

function isMutation(init = {}) {
  return ['POST', 'PUT', 'PATCH', 'DELETE'].includes(String(init.method || 'GET').toUpperCase());
}

async function rawRequest(path, init = {}) {
  const headers = { ...(init.headers || {}) };
  if (isMutation(init)) {
    const csrf = readCookie('pos_csrf');
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }
  if (!(init.body instanceof FormData) && init.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const res = await fetch(`${API_BASE}${normalizedPath}`, { cache: 'no-store', credentials: 'same-origin', ...init, headers });
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  return { res, data };
}

async function refreshBrowserSession() {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshed = await rawRequest('/auth/refresh', { method: 'POST' });
      if (!refreshed.res.ok) throw new Error(refreshed.data?.detail || 'Session expired');
      return refreshed.data;
    })().finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

async function requestOnce(path, init = {}, retrying = false) {
  const { res, data } = await rawRequest(path, init);
  if (res.status === 401 && !retrying && !String(path).startsWith('/auth/')) {
    await refreshBrowserSession();
    const retried = await rawRequest(path, init);
    if (!retried.res.ok) throw new Error(retried.data?.detail || 'Request failed');
    return retried.data;
  }
  if (!res.ok) throw new Error(data?.detail || 'Request failed');
  return data;
}

async function request(path, init = {}, retrying = false) {
  if (retrying) return requestOnce(path, init, true);
  const key = mutationRequestKey(path, init);
  if (!key) return requestOnce(path, init, false);
  const existing = mutationRegistry.get(key);
  if (existing) return existing;
  const pending = requestOnce(path, init, false);
  mutationRegistry.set(key, pending);
  try { return await pending; }
  finally { mutationRegistry.clear(key, pending); }
}

async function blobRequest(path, retrying = false) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const res = await fetch(`${API_BASE}${normalizedPath}`, { cache: 'no-store', credentials: 'same-origin' });
  if (res.status === 401 && !retrying) {
    await refreshBrowserSession();
    return blobRequest(path, true);
  }
  if (!res.ok) {
    let data = null;
    try { data = await res.json(); } catch { data = null; }
    throw new Error(data?.detail || 'Request failed');
  }
  return res.blob();
}

async function payloadWithManagerApproval(payload, { approvalType, entityType, entityId = null, reason = null }) {
  const next = { ...(payload || {}) };
  const credentials = next.approved_by_user_id;
  delete next.approved_by_user_id;
  if (credentials == null) return next;
  if (typeof credentials !== 'object' || !credentials.manager_username || !credentials.manager_password) {
    throw new Error('Manager approval must be authenticated. A manager user ID is not an approval.');
  }
  const protectedPayload = { ...next };
  delete protectedPayload.approval_grant_uuid;
  const grant = await request('/approvals/authorize', {
    method: 'POST',
    body: JSON.stringify({
      manager_username: credentials.manager_username,
      manager_password: credentials.manager_password,
      approval_type: approvalType,
      entity_type: entityType,
      entity_id: entityId,
      requested_reason: reason,
      protected_payload: protectedPayload,
    }),
  });
  return { ...next, approval_grant_uuid: grant.approval_uuid };
}

export { API_BASE, request };

export const bootstrap = () => request('/auth/bootstrap', { method: 'POST' });
export const login = (payload) => request('/auth/login', { method: 'POST', body: JSON.stringify(payload) });
export const me = () => request('/auth/me');
export const fetchUsers = () => request('/auth/users');
export const createUser = (payload) => request('/auth/users', { method: 'POST', body: JSON.stringify(payload) });
export const updateUser = (id, payload) => request(`/auth/users/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
export const fetchRoles = () => request('/auth/roles');
export const fetchPermissions = () => request('/auth/permissions');

export const getDashboard = () => request('/dashboard/summary');

export const fetchCatalogItems = (params = {}) => request(`/catalog/items${qs(params)}`);
export const createCatalogItem = (payload) => request('/catalog/items', { method: 'POST', body: JSON.stringify(payload) });
export const updateCatalogItem = (id, payload) => request(`/catalog/items/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
export const deleteCatalogItem = (id) => request(`/catalog/items/${id}`, { method: 'DELETE' });
export const syncCatalogFromAccounting = () => request('/catalog/sync-from-accounting', { method: 'POST' });
export const fetchRecipeDishes = (params = {}) => request(`/recipes/dishes${qs(params)}`);
export const fetchRecipeDocuments = (params = {}) => request(`/recipes/${qs(params)}`);
export const fetchRecipePdf = (menuItemId) => blobRequest(`/recipes/${encodeURIComponent(menuItemId)}/pdf`);
export const uploadRecipePdf = ({ menuItemId, file, title = '', notes = '' }) => request(`/recipes/${encodeURIComponent(menuItemId)}/pdf${qs({ filename: file?.name || 'recipe.pdf', title, notes })}`, { method: 'PUT', headers: { 'Content-Type': 'application/pdf' }, body: file });
export const deleteRecipePdf = (menuItemId) => request(`/recipes/${encodeURIComponent(menuItemId)}`, { method: 'DELETE' });

export const fetchOutlets = () => request('/registers/outlets');
export const createOutlet = (payload) => request('/registers/outlets', { method: 'POST', body: JSON.stringify(payload) });
export const updateOutlet = (id, payload) => request(`/registers/outlets/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
export const fetchRegisters = (activeOnly = false) => request(`/registers${qs({ active_only: !!activeOnly })}`);
export const createRegister = (payload) => request('/registers', { method: 'POST', body: JSON.stringify(payload) });
export const updateRegister = (id, payload) => request(`/registers/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
export const fetchAccountingAccounts = () => request('/registers/accounting-accounts');
export const validateAccountingAccount = (params = {}) => request(`/registers/accounting-accounts/validate${qs(params)}`);
export const fetchAccountingHealth = () => request('/registers/accounting-accounts/health');

export const fetchRegisterSessions = (params = {}) => request(`/register-sessions${qs(params)}`);
export const fetchRegisterSession = (id) => request(`/register-sessions/${id}`);
export const openRegisterSession = (payload) => request('/register-sessions/open', { method: 'POST', body: JSON.stringify(payload) });
export const closeRegisterSession = (id, payload) => request(`/register-sessions/${id}/close`, { method: 'POST', body: JSON.stringify(payload) });
export const reopenRegisterSession = async (id, payload) => {
  const secured = await payloadWithManagerApproval(payload, { approvalType: 'reopen_session', entityType: 'register_session', entityId: id, reason: payload?.reason });
  return request(`/register-sessions/${id}/reopen`, { method: 'POST', body: JSON.stringify(secured) });
};

export const fetchOrders = (params = {}) => request(`/orders${qs(params)}`);
export const fetchOrder = (id) => request(`/orders/${id}`);
export const createOrder = async (payload) => {
  const secured = await payloadWithManagerApproval(payload, { approvalType: 'discount', entityType: 'order', entityId: null, reason: 'Discounted order creation' });
  return request('/orders', { method: 'POST', body: JSON.stringify(secured) });
};
export const updateOrder = async (id, payload) => {
  const secured = await payloadWithManagerApproval(payload, { approvalType: 'discount', entityType: 'order', entityId: id, reason: 'Discounted order update' });
  return request(`/orders/${id}`, { method: 'PUT', body: JSON.stringify(secured) });
};
export const holdOrder = (id) => request(`/orders/${id}/hold`, { method: 'POST' });
export const resumeOrder = (id) => request(`/orders/${id}/resume`, { method: 'POST' });
export const transferOrderTable = (id, target) => request(`/orders/${id}/transfer-table`, { method: 'POST', body: JSON.stringify(typeof target === 'object' ? target : { target_table_label: target }) });
export const mergeOrderTable = (id, target) => request(`/orders/${id}/merge-table`, { method: 'POST', body: JSON.stringify(typeof target === 'object' ? target : { target_table_label: target }) });
export const payOrder = (id, payload) => request(`/orders/${id}/pay`, { method: 'POST', body: JSON.stringify(payload) });
export const voidOrder = async (id, payload) => {
  const secured = await payloadWithManagerApproval(payload, { approvalType: 'void', entityType: 'order', entityId: id, reason: payload?.reason });
  return request(`/orders/${id}/void`, { method: 'POST', body: JSON.stringify(secured) });
};
export const fetchRefunds = (id) => request(`/orders/${id}/refunds`);
export const createRefund = async (id, payload) => {
  const secured = await payloadWithManagerApproval(payload, { approvalType: 'refund', entityType: 'refund', entityId: id, reason: payload?.reason_text || payload?.reason_code || 'Refund' });
  return request(`/orders/${id}/refunds`, { method: 'POST', body: JSON.stringify(secured) });
};

export const fetchCashMovements = (params = {}) => request(`/cash-movements${qs(params)}`);
export const createCashMovement = async (payload) => {
  const movementType = String(payload?.movement_type || '').trim().toLowerCase();
  const secured = await payloadWithManagerApproval(payload, { approvalType: movementType === 'paid_out' ? 'cash_paid_out' : 'cash_adjustment', entityType: 'cash_movement', entityId: null, reason: payload?.note || payload?.category || movementType });
  return request('/cash-movements', { method: 'POST', body: JSON.stringify(secured) });
};

export const fetchKitchenTickets = (params = {}) => request(`/kitchen/tickets${qs(params, true)}`);
export const updateKitchenLineStatus = (id, payload) => request(`/kitchen/lines/${id}/status`, { method: 'POST', body: JSON.stringify(payload) });

export const fetchOutbox = (params = {}) => request(`/sync/outbox${qs(params)}`);
export const fetchSyncStatus = () => request('/sync/status');
export const runOutboxSync = (payload = { limit: 25 }) => request('/sync/run', { method: 'POST', body: JSON.stringify(payload) });
export const retryOutboxEvent = (eventId) => request(`/sync/retry/${eventId}`, { method: 'POST' });
export const unblockOutboxEvent = (eventId) => request(`/sync/unblock/${eventId}`, { method: 'POST' });
export const archiveOutboxEvent = (eventId, reason = 'Manual archive') => request(`/sync/archive/${eventId}`, { method: 'POST', body: JSON.stringify({ reason }) });
export const resolveOutboxEvent = (eventId, resolution = 'Manually resolved') => request(`/sync/resolve/${eventId}`, { method: 'POST', body: JSON.stringify({ resolution }) });

export const getSystemSettings = () => request('/system-settings');
export const updateSystemSettings = (payload) => request('/system-settings', { method: 'PUT', body: JSON.stringify(payload) });
export const fetchTableLayout = () => request('/system-settings/table-layout');
export const updateTableLayout = (payload) => request('/system-settings/table-layout', { method: 'PUT', body: JSON.stringify(payload) });
export const seedDefaults = () => request('/seed/defaults', { method: 'POST' });

export const refreshSession = () => request('/auth/refresh', { method: 'POST' });
export const logoutSession = () => request('/auth/logout', { method: 'POST' });

export const fetchRoomCharges = (params = {}) => request(`/room-charges${qs(params)}`);
export const fetchRoomCharge = (id) => request(`/room-charges/${id}`);
export const updateRoomChargeStatus = async (id, payload) => {
  const target = String(payload?.posting_status || '').trim().toLowerCase().replaceAll(' ', '_');
  const approvalType = target === 'disputed' ? 'room_charge_dispute' : 'room_charge_write_off';
  const secured = await payloadWithManagerApproval(payload, { approvalType, entityType: 'room_charge', entityId: id, reason: payload?.dispute_note || payload?.note || target });
  return request(`/room-charges/${id}/status`, { method: 'POST', body: JSON.stringify(secured) });
};
export const fetchInHouseBookings = (params = {}) => request(`/room-charges/in-house-bookings${qs(params)}`);
export const createInHouseBooking = (payload) => request('/room-charges/in-house-bookings', { method: 'POST', body: JSON.stringify(payload) });
export const updateInHouseBooking = (id, payload) => request(`/room-charges/in-house-bookings/${id}`, { method: 'PUT', body: JSON.stringify(payload) });

export const fetchAuditLogs = (params = {}) => request(`/audit${qs(params)}`);
export const fetchApprovals = (params = {}) => request(`/approvals${qs(params)}`);
export const fetchApproval = (id) => request(`/approvals/${id}`);
export const approveApproval = (id, payload = {}) => request(`/approvals/${id}/approve`, { method: 'POST', body: JSON.stringify(payload) });
export const rejectApproval = (id, payload = {}) => request(`/approvals/${id}/reject`, { method: 'POST', body: JSON.stringify(payload) });

export async function fetchCustomerDisplaySnapshot(channel = 'main') {
  const res = await fetch(`${API_BASE}/customer-display/${encodeURIComponent(channel)}`, { cache: 'no-store', credentials: 'same-origin' });
  if (!res.ok) throw new Error('Customer display server is unavailable.');
  return res.json();
}

export const updateCustomerDisplaySnapshot = (snapshot, channel = 'main') => request(`/customer-display/${encodeURIComponent(channel)}`, { method: 'PUT', body: JSON.stringify(snapshot) });
