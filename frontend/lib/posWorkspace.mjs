function num(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function todayISO() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

export function money(value) {
  return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export const DEFAULT_SERVICE_AREAS = ['Lobby', 'Terrace', 'Garden', 'Gazebo', 'Above Kitchen', 'Pool', 'Room Service', 'Takeout'];
export const DEFAULT_TABLES = [
  { id: 'l1', area: 'Lobby', code: 'L1', x: 16, y: 24, seats: 4, shape: 'round' },
  { id: 'l2', area: 'Lobby', code: 'L2', x: 56, y: 26, seats: 4, shape: 'round' },
  { id: 'lounge', area: 'Lobby', code: 'Lounge', x: 32, y: 62, seats: 6, shape: 'sofa' },
  { id: 'tr1', area: 'Terrace', code: 'TR1', x: 12, y: 22, seats: 2, shape: 'umbrella' },
  { id: 'tr2', area: 'Terrace', code: 'TR2', x: 46, y: 26, seats: 4, shape: 'umbrella' },
  { id: 'tr3', area: 'Terrace', code: 'TR3', x: 72, y: 58, seats: 4, shape: 'square' },
  { id: 'g1', area: 'Garden', code: 'G1', x: 16, y: 30, seats: 4, shape: 'umbrella' },
  { id: 'g2', area: 'Garden', code: 'G2', x: 48, y: 18, seats: 4, shape: 'umbrella' },
  { id: 'g3', area: 'Garden', code: 'G3', x: 68, y: 64, seats: 6, shape: 'round' },
  { id: 'gz1', area: 'Gazebo', code: 'Gazebo 1', x: 30, y: 36, seats: 8, shape: 'gazebo' },
  { id: 'gz2', area: 'Gazebo', code: 'Gazebo 2', x: 66, y: 58, seats: 6, shape: 'gazebo' },
  { id: 'ak1', area: 'Above Kitchen', code: 'AK1', x: 18, y: 24, seats: 4, shape: 'square' },
  { id: 'ak2', area: 'Above Kitchen', code: 'AK2', x: 58, y: 28, seats: 4, shape: 'square' },
  { id: 'ak3', area: 'Above Kitchen', code: 'AK3', x: 42, y: 66, seats: 6, shape: 'rectangle' },
  { id: 'p1', area: 'Pool', code: 'Pool 1', x: 18, y: 26, seats: 4, shape: 'umbrella' },
  { id: 'p2', area: 'Pool', code: 'Pool 2', x: 52, y: 24, seats: 4, shape: 'umbrella' },
  { id: 'cabana', area: 'Pool', code: 'Cabana', x: 68, y: 66, seats: 6, shape: 'cabana' },
];
export const TABLE_SHAPES = ['round', 'square', 'rectangle', 'umbrella', 'gazebo', 'cabana', 'sofa'];
export const MAP_ELEMENT_SHAPES = ['rectangle', 'circle', 'oval', 'triangle', 'line', 'wall', 'counter', 'bar', 'pool', 'plant', 'path', 'label'];
export const MAP_ELEMENT_COLORS = ['#dcefe4', '#dbeafe', '#fde68a', '#fecdd3', '#ddd6fe', '#e5e7eb', '#bbf7d0', '#bae6fd'];
export const QUICK_PAY_AMOUNTS = [100, 200, 500, 1000];
export const QUICK_QTY = [1, 2, 3, 4, 6, 8, 10, 12];
export const PAX_PRESETS = [1, 2, 3, 4, 5, 6, 8];
export const PAYPAD = ['7', '8', '9', '4', '5', '6', '1', '2', '3', '00', '0', '.'];
export const CASH_DENOMS = [1000, 500, 200, 100, 50, 20, 10, 5, 1];
export const TENDERS = ['cash', 'gcash', 'card', 'bank_transfer', 'room_charge'];
export const TENDER_LABELS = { cash: 'Cash', gcash: 'GCash', card: 'Card', bank_transfer: 'Bank transfer', room_charge: 'Room charge' };
export const ORDER_TYPE_LABELS = { dine_in: 'Dine-in', takeout: 'Takeout', delivery: 'Delivery', room_service: 'Room service' };
export const ROOM_CHARGE_SERVICE_TYPES = [
  { value: 'room_service', label: 'Room service' },
  { value: 'signed_from_cafe', label: 'Guest signed from café / restaurant' },
];
export const TENDER_ACCOUNT_HINTS = {
  cash: 'Drawer account',
  gcash: 'GCash receiving account',
  card: 'Card clearing account',
  bank_transfer: 'Bank account / clearing',
  room_charge: 'No cashier settlement account',
};
export const PRIMARY_QUEUE_VIEWS = ['priority', 'this_area', 'unpaid'];
export const SECONDARY_QUEUE_VIEWS = ['all_open', 'held', 'all_tables', 'newest', 'oldest'];
export const ACTIVE_TABLE_ORDER_STATUSES = ['draft', 'held', 'open', 'sent', 'served', 'unpaid'];
export const QUEUE_VIEW_LABELS = {
  priority: 'Priority',
  this_area: 'This Area',
  unpaid: 'Unpaid',
  all_open: 'All Open',
  held: 'Held',
  all_tables: 'All Tables',
  newest: 'Newest',
  oldest: 'Oldest',
};

export function findSafeDropAccount(accounts) {
  const rows = Array.isArray(accounts) ? accounts : [];
  return rows.find((row) => /safe|vault|cash in safe|bank|deposit/i.test(`${row.name || ''} ${row.account_name || ''} ${row.code || ''}`)) || null;
}

export function emptyPayment(total = '', accountId = '') {
  return { tender_type: 'cash', amount_applied: String(total || ''), amount_received: String(total || ''), reference_no: '', accounting_financial_account_id: String(accountId || ''), room_charge_service_type: 'room_service', room_charge_booking_date: todayISO(), room_charge_service_date: todayISO(), room_charge_room_number: '', room_charge_guest_label: '', room_charge_beds24_booking_id: '', room_charge_order_source: 'room_service', room_charge_note: '', room_charge_bill_to: '', room_charge_booking_snapshot_id: '', room_charge_picker_query: '' };
}

export function lineGross(line) { return num(line.price) * num(line.quantity); }
export function calculateCartTotals(lines = []) {
  const totals = lines.reduce((result, line) => {
    const gross = lineGross(line);
    const discount = Math.min(Math.max(num(line.discount_amount), 0), gross);
    const net = Math.max(gross - discount, 0);
    result.subtotal += gross;
    result.discount += discount;
    result.tax += net * Math.max(num(line.tax_rate), 0);
    result.serviceCharge += net * Math.max(num(line.service_charge_rate), 0);
    return result;
  }, { subtotal: 0, discount: 0, tax: 0, serviceCharge: 0 });
  for (const key of Object.keys(totals)) totals[key] = Math.round(totals[key] * 100) / 100;
  totals.total = Math.round(Math.max(totals.subtotal - totals.discount + totals.tax + totals.serviceCharge, 0) * 100) / 100;
  return totals;
}
export function isMapVisualElement(item) { return item?.kind === 'element' || item?.type === 'element' || item?.is_visual === true; }

function parseMaybeJson(raw) {
  if (!raw) return null;
  const text = String(raw).trim();
  const candidate = text.startsWith('POSCFG:') ? text.slice(7).trim() : text;
  if (!candidate.startsWith('{')) return null;
  try { return JSON.parse(candidate); } catch { return null; }
}

export function itemPhotoUrl(item) {
  const parsed = parseMaybeJson(item?.notes);
  return item?.image_url || item?.photo_url || item?.thumbnail_url || item?.menu_photo_url || parsed?.image_url || parsed?.photo_url || parsed?.thumbnail_url || '';
}

export function groupPriceLabel(group) {
  const prices = (group?.items || []).map((item) => num(item.price)).filter((value) => Number.isFinite(value));
  if (!prices.length) return money(0);
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  return low === high ? money(low) : `${money(low)}-${money(high)}`;
}

export function lineDetailParts(line) { return String(line?.note || '').split(' · ').map((part) => part.trim()).filter(Boolean); }

export function serviceLabel(status, orderStatus) {
  const value = String(status || orderStatus || '').toLowerCase();
  if (value === 'held') return 'Held';
  if (['draft', 'open'].includes(value)) return 'New';
  if (['sent', 'ordered', 'preparing'].includes(value)) return 'Waiting';
  if (value === 'ready') return 'Ready';
  if (value === 'served') return 'Served';
  if (['unpaid', 'billing', 'folio_pending'].includes(value)) return 'Billing';
  if (['paid', 'closed'].includes(value)) return 'Closed';
  return value ? value[0].toUpperCase() + value.slice(1) : 'New';
}

export function elapsedLabel(minutes) {
  const value = num(minutes, 0);
  if (!value) return 'Just now';
  if (value < 60) return `${value}m`;
  const hours = Math.floor(value / 60);
  const mins = value % 60;
  return `${hours}h${mins ? ` ${mins}m` : ''}`;
}

export function tableKey(area, code) { return `${String(area || '').trim()}::${String(code || '').trim()}`; }
export function tableValue(table) { return tableKey(table?.area, table?.code); }
export function parseTableValue(value) {
  const text = String(value || '');
  if (!text.includes('::')) return { area: '', code: text.trim() };
  const [area, ...rest] = text.split('::');
  return { area: area.trim(), code: rest.join('::').trim() };
}
