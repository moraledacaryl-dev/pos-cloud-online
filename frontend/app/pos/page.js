"use client";

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  createOrder,
  closeRegisterSession,
  createCashMovement,
  fetchAccountingAccounts,
  fetchCatalogItems,
  fetchInHouseBookings,
  fetchOrder,
  fetchOrders,
  fetchRegisterSessions,
  fetchRegisters,
  fetchSyncStatus,
  fetchTableLayout,
  holdOrder,
  mergeOrderTable,
  openRegisterSession,
  payOrder,
  resumeOrder,
  transferOrderTable,
  updateCatalogItem,
  updateCustomerDisplaySnapshot,
  updateOrder,
  updateTableLayout,
} from '../../lib/api';
import {
  applyPromotion,
  buildConfiguredLine,
  createDefaultSelections,
  getProductProfile,
  getPromotionSuggestions,
  num,
  recalcLine,
  resetPromotions,
  serializeCustomerDisplay,
  updateLineWithDiscount,
} from '../../lib/terminalProfiles';
import { loadLastReceipt, printCloseSessionPacket, printReceipt, saveLastReceipt } from '../../lib/receipt';
import { listOfflineDrafts, removeOfflineDraft, saveOfflineDraft } from '../../lib/offlineDrafts';
import ManagerOverrideModal from '../../components/ManagerOverrideModal';
import { applyKeypadInput, calculatePaymentModal, findRoomChargeBookingMatches, pickRoomChargeBooking, rankCatalogItems, summarizeTerminalHealth } from '../../lib/ui_contracts.mjs';

function todayISO() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}
function money(value) { return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

const DEFAULT_SERVICE_AREAS = ['Lobby', 'Terrace', 'Garden', 'Gazebo', 'Above Kitchen', 'Pool', 'Room Service', 'Takeout'];
const DEFAULT_TABLES = [
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
const TABLE_SHAPES = ['round', 'square', 'rectangle', 'umbrella', 'gazebo', 'cabana', 'sofa'];
const MAP_ELEMENT_SHAPES = ['rectangle', 'circle', 'oval', 'triangle', 'line', 'wall', 'counter', 'bar', 'pool', 'plant', 'path', 'label'];
const MAP_ELEMENT_COLORS = ['#dcefe4', '#dbeafe', '#fde68a', '#fecdd3', '#ddd6fe', '#e5e7eb', '#bbf7d0', '#bae6fd'];
const QUICK_PAY_AMOUNTS = [100, 200, 500, 1000];
const QUICK_QTY = [1, 2, 3, 4, 6, 8, 10, 12];
const PAX_PRESETS = [1, 2, 3, 4, 5, 6, 8];
const PAYPAD = ['7', '8', '9', '4', '5', '6', '1', '2', '3', '00', '0', '.'];
const CASH_DENOMS = [1000, 500, 200, 100, 50, 20, 10, 5, 1];
const TENDERS = ['cash', 'gcash', 'card', 'bank_transfer', 'room_charge'];
const TENDER_LABELS = {
  cash: 'Cash',
  gcash: 'GCash',
  card: 'Card',
  bank_transfer: 'Bank transfer',
  room_charge: 'Room charge',
};
const ORDER_TYPE_LABELS = {
  dine_in: 'Dine-in',
  takeout: 'Takeout',
  delivery: 'Delivery',
  room_service: 'Room service',
};
const ROOM_CHARGE_SERVICE_TYPES = [{ value: 'room_service', label: 'Room service' }, { value: 'signed_from_cafe', label: 'Guest signed from café / restaurant' }];
const TENDER_ACCOUNT_HINTS = {
  cash: 'Drawer account',
  gcash: 'GCash receiving account',
  card: 'Card clearing account',
  bank_transfer: 'Bank account / clearing',
  room_charge: 'No cashier settlement account',
};
const PRIMARY_QUEUE_VIEWS = ['priority', 'this_area', 'unpaid'];
const SECONDARY_QUEUE_VIEWS = ['all_open', 'held', 'all_tables', 'newest', 'oldest'];
const ACTIVE_TABLE_ORDER_STATUSES = ['draft', 'held', 'open', 'sent', 'served', 'unpaid'];
const QUEUE_VIEW_LABELS = {
  priority: 'Priority',
  this_area: 'This Area',
  unpaid: 'Unpaid',
  all_open: 'All Open',
  held: 'Held',
  all_tables: 'All Tables',
  newest: 'Newest',
  oldest: 'Oldest',
};

function findSafeDropAccount(accounts) {
  const rows = Array.isArray(accounts) ? accounts : [];
  return rows.find((row) => /safe|vault|cash in safe|bank|deposit/i.test(`${row.name || ''} ${row.account_name || ''} ${row.code || ''}`)) || null;
}

function emptyPayment(total = '', accountId = '') {
  return { tender_type: 'cash', amount_applied: String(total || ''), amount_received: String(total || ''), reference_no: '', accounting_financial_account_id: String(accountId || ''), room_charge_service_type: 'room_service', room_charge_booking_date: todayISO(), room_charge_service_date: todayISO(), room_charge_room_number: '', room_charge_guest_label: '', room_charge_beds24_booking_id: '', room_charge_order_source: 'room_service', room_charge_note: '', room_charge_bill_to: '', room_charge_booking_snapshot_id: '', room_charge_picker_query: '' };
}
function lineGross(line) { return num(line.price) * num(line.quantity); }
function isMapVisualElement(item) { return item?.kind === 'element' || item?.type === 'element' || item?.is_visual === true; }
function parseMaybeJson(raw) {
  if (!raw) return null;
  const text = String(raw).trim();
  const candidate = text.startsWith('POSCFG:') ? text.slice(7).trim() : text;
  if (!candidate.startsWith('{')) return null;
  try { return JSON.parse(candidate); } catch { return null; }
}
function itemPhotoUrl(item) {
  const parsed = parseMaybeJson(item?.notes);
  return item?.image_url || item?.photo_url || item?.thumbnail_url || item?.menu_photo_url || parsed?.image_url || parsed?.photo_url || parsed?.thumbnail_url || '';
}
function groupPriceLabel(group) {
  const prices = (group?.items || []).map((item) => num(item.price)).filter((value) => Number.isFinite(value));
  if (!prices.length) return money(0);
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  return low === high ? money(low) : `${money(low)}-${money(high)}`;
}
function lineDetailParts(line) {
  return String(line?.note || '').split(' · ').map((part) => part.trim()).filter(Boolean);
}
function serviceLabel(status, orderStatus) {
  const value = String(status || orderStatus || '').toLowerCase();
  if (value === 'held') return 'Held';
  if (['draft', 'open'].includes(value)) return 'New';
  if (['sent', 'ordered', 'preparing'].includes(value)) return 'Waiting';
  if (['ready'].includes(value)) return 'Ready';
  if (['served'].includes(value)) return 'Served';
  if (['unpaid', 'billing', 'folio_pending'].includes(value)) return 'Billing';
  if (['paid', 'closed'].includes(value)) return 'Closed';
  return value ? value[0].toUpperCase() + value.slice(1) : 'New';
}
function elapsedLabel(minutes) {
  const value = num(minutes, 0);
  if (!value) return 'Just now';
  if (value < 60) return `${value}m`;
  const hours = Math.floor(value / 60);
  const mins = value % 60;
  return `${hours}h${mins ? ` ${mins}m` : ''}`;
}
function tableKey(area, code) {
  return `${String(area || '').trim()}::${String(code || '').trim()}`;
}
function tableValue(table) {
  return tableKey(table?.area, table?.code);
}
function parseTableValue(value) {
  const text = String(value || '');
  if (!text.includes('::')) return { area: '', code: text.trim() };
  const [area, ...rest] = text.split('::');
  return { area: area.trim(), code: rest.join('::').trim() };
}

export default function PosPage() {
  const searchParams = useSearchParams();
  const requestedOrderId = searchParams.get('order_id');
  const [catalog, setCatalog] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [registers, setRegisters] = useState([]);
  const [accountingAccounts, setAccountingAccounts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [inHouseBookings, setInHouseBookings] = useState([]);
  const [sessionId, setSessionId] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [search, setSearch] = useState('');
  const [barcode, setBarcode] = useState('');
  const [cart, setCart] = useState([]);
  const [guestName, setGuestName] = useState('');
  const [tableLabel, setTableLabel] = useState('');
  const [activeArea, setActiveArea] = useState('Lobby');
  const [tableLayout, setTableLayout] = useState({ areas: DEFAULT_SERVICE_AREAS, tables: DEFAULT_TABLES });
  const [mapEditor, setMapEditor] = useState({ editing: false, selectedId: '', draggingId: '' });
  const [mapManagerOpen, setMapManagerOpen] = useState(false);
  const [terminalLayout, setTerminalLayout] = useState('map-wide');
  const [terminalScreen, setTerminalScreen] = useState('spaces');
  const [serviceQueueView, setServiceQueueView] = useState('priority');
  const [orderType, setOrderType] = useState('dine_in');
  const [seatCount, setSeatCount] = useState('');
  const [note, setNote] = useState('');
  const [payments, setPayments] = useState([emptyPayment()]);
  const [currentOrderId, setCurrentOrderId] = useState(null);
  const [currentOrderNo, setCurrentOrderNo] = useState('');
  const [receiptPreview, setReceiptPreview] = useState(null);
  const [selectedLineId, setSelectedLineId] = useState(null);
  const [openSessionForm, setOpenSessionForm] = useState({ register_id: '', business_date: todayISO(), shift_name: 'AM', opening_float: '0', opening_note: '' });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [lastReceipt, setLastReceipt] = useState(null);
  const [browserOnline, setBrowserOnline] = useState(true);
  const [offlineDrafts, setOfflineDrafts] = useState([]);
  const [terminalHealth, setTerminalHealth] = useState(null);
  const [terminalHealthError, setTerminalHealthError] = useState('');
  const [closedSessionPacket, setClosedSessionPacket] = useState(null);
  const [paymentPad, setPaymentPad] = useState({ paymentIndex: 0, target: 'amount_received' });
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [configurator, setConfigurator] = useState({ open: false, group: null, item: null, profile: null, selections: null });
  const [assignTablePrompt, setAssignTablePrompt] = useState({ open: false, targetTable: '', pax: '', groupName: '' });
  const [tableAction, setTableAction] = useState({ open: false, mode: '', table: null, order: null, groupName: '', pax: '', targetTable: '' });
  const [lineEditor, setLineEditor] = useState({ open: false, lineId: '' });
  const [availabilityOpen, setAvailabilityOpen] = useState(false);
  const [availabilitySearch, setAvailabilitySearch] = useState('');
  const [variantPicker, setVariantPicker] = useState({ open: false, label: '', items: [], action: 'order' });
  const [quickClose, setQuickClose] = useState({ open: false, closing_actual_cash: '', closing_note: '', variance_note: '', sign_off_name: '', sign_off_role: '', print_packet: true, manual_total: false, denominations: {} });
  const [moneyDrop, setMoneyDrop] = useState({ open: false, amount: '', to_accounting_financial_account_id: '', note: '', reference_no: '' });
  const [paidOut, setPaidOut] = useState({ open: false, amount: '', category: 'Emergency Purchase', note: '', reference_no: '' });
  const [overrideModal, setOverrideModal] = useState({ open: false, title: '', subtitle: '' });
  const [discountApprovalUserId, setDiscountApprovalUserId] = useState(null);
  const overrideActionRef = useRef(null);
  const barcodeRef = useRef(null);
  const searchRef = useRef(null);

  async function loadAll({ silent = false } = {}) {
    if (!silent) setLoading(true);
    try {
      const [catalogRows, sessionRows, orderRows, registerRows, accountRows] = await Promise.all([
        fetchCatalogItems({ active_only: true }),
        fetchRegisterSessions({ status: 'open', limit: 50 }),
        fetchOrders({ limit: 120 }),
        fetchRegisters(true),
        fetchAccountingAccounts().catch(() => []),
      ]);
      setCatalog(Array.isArray(catalogRows) ? catalogRows : []);
      const openRows = Array.isArray(sessionRows) ? sessionRows : [];
      setSessions(openRows);
      if (!sessionId && openRows[0]?.id) setSessionId(String(openRows[0].id));
      setOrders(Array.isArray(orderRows) ? orderRows : []);
      setRegisters(Array.isArray(registerRows) ? registerRows : []);
      setAccountingAccounts(Array.isArray(accountRows) ? accountRows : []);
      if (!openSessionForm.register_id && registerRows?.[0]?.id) setOpenSessionForm((prev) => ({ ...prev, register_id: String(registerRows[0].id) }));
    } catch (e) {
      setError(e.message || 'Failed to load POS data.');
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => { loadAll().catch(console.error); setLastReceipt(loadLastReceipt()); setOfflineDrafts(listOfflineDrafts()); }, []);
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const updateStatus = () => setBrowserOnline(window.navigator.onLine !== false);
    updateStatus();
    window.addEventListener('online', updateStatus);
    window.addEventListener('offline', updateStatus);
    return () => {
      window.removeEventListener('online', updateStatus);
      window.removeEventListener('offline', updateStatus);
    };
  }, []);
  useEffect(() => {
    if (!browserOnline) return undefined;
    let active = true;
    async function loadHealth() {
      try {
        const data = await fetchSyncStatus();
        if (!active) return;
        setTerminalHealth(data || null);
        setTerminalHealthError('');
      } catch (e) {
        if (!active) return;
        setTerminalHealthError(e.message || 'Could not read POS health.');
      }
    }
    loadHealth().catch(console.error);
    const timer = window.setInterval(() => loadHealth().catch(console.error), 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [browserOnline]);
  useEffect(() => {
    fetchTableLayout()
      .then((layout) => {
        const areas = Array.isArray(layout?.areas) && layout.areas.length ? layout.areas : DEFAULT_SERVICE_AREAS;
        const tables = Array.isArray(layout?.tables) ? layout.tables : DEFAULT_TABLES;
        setTableLayout({ areas, tables });
        if (!areas.includes(activeArea)) setActiveArea(areas[0] || 'Lobby');
      })
      .catch(() => setTableLayout({ areas: DEFAULT_SERVICE_AREAS, tables: DEFAULT_TABLES }));
  }, []);
  useEffect(() => { if (!requestedOrderId) return; fetchOrder(requestedOrderId).then((order) => { if (order?.id) loadOrderIntoCart(order, false); }).catch(() => {}); }, [requestedOrderId]);
  useEffect(() => {
    function onKeyDown(event) {
      const tag = document.activeElement?.tagName;
      if (paymentOpen && event.key === '+') { event.preventDefault(); addPaymentRow(); }
      if (event.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA') { event.preventDefault(); searchRef.current?.focus(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); handleSaveDraft('draft'); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'h') { event.preventDefault(); handleSaveDraft('held'); }
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); handlePay(); }
      if (event.key === 'F8') { event.preventDefault(); barcodeRef.current?.focus(); }
      if (event.key === 'F9') { event.preventDefault(); addQuickAmount(cartTotals.total); }
      if (event.key === 'Escape') { setConfigurator((prev) => ({ ...prev, open: false })); setPaymentOpen(false); setMapManagerOpen(false); setMapEditor((prev) => ({ ...prev, editing: false, draggingId: '' })); setTableAction((prev) => ({ ...prev, open: false })); setLineEditor((prev) => ({ ...prev, open: false })); setOverrideModal((prev) => ({ ...prev, open: false })); }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });
  useEffect(() => {
    if (!paymentOpen || typeof window === 'undefined') return undefined;
    const timer = window.setTimeout(() => {
      document.querySelector('.payment-terminal-modal input:not([disabled])')?.focus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [paymentOpen]);

  const categories = useMemo(() => ['Popular', 'All', ...Array.from(new Set(catalog.map((item) => item.category_name || 'Uncategorized')))], [catalog]);
  const filteredCatalog = useMemo(() => {
    if (selectedCategory === 'Popular') return rankCatalogItems(catalog.filter((item) => item.is_available !== false), { query: search, category: 'All' }).slice(0, 24);
    return rankCatalogItems(catalog, { query: search, category: selectedCategory });
  }, [catalog, selectedCategory, search]);
  const productGroups = useMemo(() => {
    const groups = new Map();
    filteredCatalog.forEach((item) => {
      const key = item.external_menu_item_id ? `external:${item.external_menu_item_id}` : `name:${item.menu_item_name || item.display_name || item.id}`;
      const label = item.menu_item_name || item.display_name || `Item ${item.id}`;
      if (!groups.has(key)) groups.set(key, { key, label, items: [] });
      groups.get(key).items.push(item);
    });
    return Array.from(groups.values()).map((group) => {
      const items = group.items.sort((a, b) => getVariantLabel(a).localeCompare(getVariantLabel(b)));
      const representative = items.find((item) => itemPhotoUrl(item)) || items[0];
      const profile = getProductProfile(representative);
      const availableItems = items.filter((item) => item.is_available !== false);
      return {
        ...group,
        items,
        availableItems,
        representative,
        photo_url: itemPhotoUrl(representative),
        is_available: availableItems.length > 0,
        has_options: availableItems.length > 1 || !!(profile?.modifier_groups || []).length || !!(profile?.bundle_choices || []).length || !!profile?.prompt_note_label,
      };
    });
  }, [filteredCatalog]);
  const availabilityRows = useMemo(() => {
    const q = availabilitySearch.trim().toLowerCase();
    return catalog
      .filter((item) => !q || `${item.display_name || ''} ${item.menu_item_name || ''} ${item.category_name || ''} ${item.variant_name || ''}`.toLowerCase().includes(q))
      .sort((a, b) => (a.category_name || '').localeCompare(b.category_name || '') || (a.menu_item_name || a.display_name || '').localeCompare(b.menu_item_name || b.display_name || ''));
  }, [availabilitySearch, catalog]);
  const currentSession = useMemo(() => sessions.find((row) => String(row.id) === String(sessionId)) || null, [sessions, sessionId]);
  const currentRegister = useMemo(() => registers.find((row) => String(row.id) === String(currentSession?.register_id || '')) || null, [registers, currentSession]);
  const terminalHealthSummary = useMemo(() => summarizeTerminalHealth(terminalHealth, { online: browserOnline, error: terminalHealthError, offlineDraftsCount: offlineDrafts.length }), [terminalHealth, browserOnline, terminalHealthError, offlineDrafts.length]);
  useEffect(() => {
    const stayDate = currentSession?.business_date || todayISO();
    fetchInHouseBookings({ stay_date: stayDate, active_only: true, limit: 100 }).then((rows) => setInHouseBookings(Array.isArray(rows) ? rows : [])).catch(() => setInHouseBookings([]));
  }, [currentSession?.business_date]);
  const currentRoomServiceBooking = useMemo(() => {
    const room = String(tableLabel || '').trim().toLowerCase();
    const guest = String(guestName || '').trim().toLowerCase();
    if (!room && !guest) return null;
    return inHouseBookings.find((row) => {
      const rowRoom = String(row.room_number || '').trim().toLowerCase();
      const rowGuest = String(row.guest_label || row.guest_name || '').trim().toLowerCase();
      return (room && rowRoom === room) || (guest && rowGuest === guest);
    }) || null;
  }, [inHouseBookings, tableLabel, guestName]);
  const cartTotals = useMemo(() => {
    const subtotal = cart.reduce((sum, line) => sum + lineGross(line), 0);
    const discount = cart.reduce((sum, line) => sum + num(line.discount_amount), 0);
    return { subtotal, discount, total: Math.max(subtotal - discount, 0) };
  }, [cart]);
  const totalApplied = useMemo(() => payments.reduce((sum, row) => sum + num(row.amount_applied), 0), [payments]);
  const folioApplied = useMemo(() => payments.filter((row) => row.tender_type === 'room_charge').reduce((sum, row) => sum + num(row.amount_applied), 0), [payments]);
  const heldOrders = useMemo(() => orders.filter((row) => row.status === 'held' || row.status === 'draft'), [orders]);
  const selectedLine = useMemo(() => cart.find((row) => row.local_id === selectedLineId) || null, [cart, selectedLineId]);
  const totalChange = useMemo(() => payments.reduce((sum, row) => sum + Math.max(num(row.amount_received) - num(row.amount_applied), 0), 0), [payments]);
  const paymentSummary = useMemo(() => calculatePaymentModal(cartTotals.total, payments), [cartTotals.total, payments]);
  const activePayment = payments[paymentPad.paymentIndex] || payments[0] || emptyPayment();
  const promoSuggestions = useMemo(() => getPromotionSuggestions(cart, orderType), [cart, orderType]);
  const tableStatus = useMemo(() => {
    const map = {};
    orders.filter((order) => ACTIVE_TABLE_ORDER_STATUSES.includes(order.status)).forEach((order) => {
      if (!order.table_label) return;
      map[tableKey(order.service_area || '', order.table_label)] = order;
      if (!order.service_area) map[order.table_label] = order;
    });
    return map;
  }, [orders]);
  const serviceAreas = useMemo(() => {
    const areas = Array.isArray(tableLayout.areas) && tableLayout.areas.length ? tableLayout.areas : DEFAULT_SERVICE_AREAS;
    return DEFAULT_SERVICE_AREAS.filter((area) => areas.includes(area)).concat(areas.filter((area) => !DEFAULT_SERVICE_AREAS.includes(area)));
  }, [tableLayout.areas]);
  const mapServiceTables = useMemo(() => (tableLayout.tables || []).filter((table) => !isMapVisualElement(table)), [tableLayout.tables]);
  const areaTables = useMemo(() => mapServiceTables.filter((table) => table.area === activeArea), [activeArea, mapServiceTables]);
  const areaMapElements = useMemo(() => (tableLayout.tables || []).filter((item) => item.area === activeArea && isMapVisualElement(item)), [activeArea, tableLayout.tables]);
  const availableAssignmentTables = useMemo(() => mapServiceTables.filter((table) => {
    const activeOrder = tableStatus[tableValue(table)] || tableStatus[table.code];
    if (!activeOrder) return true;
    return currentOrderId && String(activeOrder.id) === String(currentOrderId);
  }), [currentOrderId, mapServiceTables, tableStatus]);
  const needsTableAssignment = orderType === 'dine_in' && !String(tableLabel || '').trim();
  const selectedMapTable = useMemo(() => (tableLayout.tables || []).find((table) => table.id === mapEditor.selectedId) || null, [mapEditor.selectedId, tableLayout.tables]);
  const serviceQueueItems = useMemo(() => {
    const tableAreaByCode = new Map(mapServiceTables.map((table) => [table.code, table.area]));
    const openRows = orders.filter((order) => ACTIVE_TABLE_ORDER_STATUSES.includes(order.status));
    const orderRows = openRows.map((order) => {
      const area = order.service_area || tableAreaByCode.get(order.table_label) || (order.order_type === 'room_service' ? 'Room Service' : order.order_type === 'takeout' ? 'Takeout' : 'Unassigned');
      const openedAt = order.created_at || order.opened_at || order.business_date;
      const ageMinutes = openedAt ? Math.max(0, Math.floor((Date.now() - new Date(openedAt).getTime()) / 60000)) : 0;
      const unpaid = num(order.balance_due ?? order.total_amount, 0);
      const status = order.kitchen_status || order.status || 'open';
      let priority = ageMinutes;
      if (['draft', 'open', 'sent'].includes(status)) priority += 40;
      if (order.status === 'held') priority += 25;
      if (unpaid > 0) priority += 15;
      if (['served', 'paid', 'closed'].includes(status)) priority -= 30;
      const label = serviceLabel(status, order.status);
      const urgency = priority > 70 ? 'urgent' : priority > 35 ? 'watch' : 'normal';
      return { kind: 'order', order, area, name: order.table_label || ORDER_TYPE_LABELS[order.order_type] || 'Walk-in', guest: order.guest_name || '', pax: order.seat_count || '', status, statusLabel: label, unpaid, ageMinutes, priority, urgency };
    });
    const emptyTableRows = mapServiceTables.map((table) => {
      const activeOrder = tableStatus[tableValue(table)] || tableStatus[table.code];
      return { kind: 'table', table, area: table.area, name: table.code, guest: activeOrder?.guest_name || '', pax: activeOrder?.seat_count || table.seats, status: activeOrder ? activeOrder.status : 'empty', statusLabel: activeOrder ? serviceLabel(activeOrder.status, activeOrder.status) : 'Available', unpaid: num(activeOrder?.total_amount, 0), ageMinutes: 0, priority: activeOrder ? 20 : -10, urgency: activeOrder ? 'watch' : 'normal' };
    });
    let rows = serviceQueueView === 'all_tables' ? emptyTableRows : orderRows;
    if (serviceQueueView === 'this_area') rows = rows.filter((row) => row.area === activeArea);
    if (serviceQueueView === 'held') rows = rows.filter((row) => row.status === 'held');
    if (serviceQueueView === 'unpaid') rows = rows.filter((row) => row.unpaid > 0);
    if (serviceQueueView === 'all_open') rows = orderRows;
    rows.sort((a, b) => serviceQueueView === 'oldest' ? b.ageMinutes - a.ageMinutes : serviceQueueView === 'newest' ? a.ageMinutes - b.ageMinutes : b.priority - a.priority);
    return rows;
  }, [activeArea, mapServiceTables, orders, serviceQueueView, tableStatus]);
  const selectedConfigGroups = configurator.profile ? [...(configurator.profile.modifier_groups || []), ...(configurator.profile.bundle_choices || [])] : [];
  const configuratorTotal = useMemo(() => {
    if (!configurator.item || !configurator.selections) return 0;
    let unit = num(configurator.item.price);
    selectedConfigGroups.forEach((group) => {
      const current = configurator.selections.selected[group.id];
      (group.options || []).forEach((option) => {
        const picked = group.mode === 'multi' ? Array.isArray(current) && current.includes(option.label) : current === option.label;
        if (picked) unit += num(option.price_delta);
      });
    });
    return Math.max(1, num(configurator.selections.quantity, 1)) * unit;
  }, [configurator.item, configurator.selections, selectedConfigGroups]);
  const getRoomChargeMatches = (row) => findRoomChargeBookingMatches(inHouseBookings, {
    stayDate: row.room_charge_booking_date || currentSession?.business_date || todayISO(),
    roomNumber: row.room_charge_room_number || '',
    guestName: row.room_charge_guest_label || '',
    query: row.room_charge_picker_query || '',
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const snapshot = serializeCustomerDisplay({ cart, totals: cartTotals, guestName, tableLabel, orderType, currentOrderNo });
    localStorage.setItem('pos_customer_display', JSON.stringify(snapshot));
    const timer = window.setTimeout(() => updateCustomerDisplaySnapshot(snapshot).catch(() => {}), 250);
    return () => window.clearTimeout(timer);
  }, [cart, cartTotals, guestName, tableLabel, orderType, currentOrderNo]);

  function openCustomerDisplay() { window.open('/customer-display?channel=main', '_blank', 'width=900,height=700'); }
  function openMapManager() { setMapManagerOpen(true); setMapEditor((prev) => ({ ...prev, editing: true, draggingId: '' })); }
  function queueManagerOverride({ title, subtitle, onApproved }) { overrideActionRef.current = onApproved; setOverrideModal({ open: true, title, subtitle }); }
  async function handleOverrideApproved(user) { const action = overrideActionRef.current; overrideActionRef.current = null; if (action) await action(user); }
  function requestDiscountApproval(nextDiscount, applyFn) {
    const gross = selectedLine ? lineGross(selectedLine) : cartTotals.total;
    const requiresOverride = num(nextDiscount) > 0 && (num(nextDiscount) > 500 || (gross > 0 && (num(nextDiscount) / gross) > 0.10));
    if (!requiresOverride) return applyFn();
    queueManagerOverride({ title: 'Manager Override Needed', subtitle: 'Discounts above 10% or above ₱500 require a manager or owner login.', onApproved: (user) => { setDiscountApprovalUserId(user?.id || null); applyFn(user); } });
  }

  function openConfiguratorForItem(item, group = null) {
    const profile = getProductProfile(item);
    setConfigurator({ open: true, group, item, profile, selections: createDefaultSelections(profile) });
  }
  function getVariantLabel(item) { return item?.variant_name || item?.sku_code || item?.display_name || item?.menu_item_name || `Item ${item?.id || ''}`; }
  function chooseProductGroup(group) {
    const items = (group.availableItems?.length ? group.availableItems : group.items || []).filter((item) => item.is_available !== false);
    if (!items.length) return setNotice(`${group.label} is sold out. Restore it from Tools > Menu Availability.`);
    openConfiguratorForItem(items[0], { ...group, items });
  }
  function groupForCatalogItem(item) {
    if (!item) return null;
    const items = catalog.filter((candidate) => (
      item.external_menu_item_id
        ? String(candidate.external_menu_item_id || '') === String(item.external_menu_item_id)
        : String(candidate.menu_item_name || candidate.display_name || candidate.id) === String(item.menu_item_name || item.display_name || item.id)
    )).sort((a, b) => getVariantLabel(a).localeCompare(getVariantLabel(b)));
    return { key: item.external_menu_item_id ? `external:${item.external_menu_item_id}` : `name:${item.menu_item_name || item.display_name || item.id}`, label: item.menu_item_name || item.display_name || `Item ${item.id}`, items, availableItems: items.filter((row) => row.is_available !== false), representative: item, photo_url: itemPhotoUrl(item), is_available: items.some((row) => row.is_available !== false), has_options: items.length > 1 };
  }
  function selectionsFromLine(line, profile) {
    const defaults = createDefaultSelections(profile);
    const selected = { ...defaults.selected };
    const allGroups = [...(profile?.modifier_groups || []), ...(profile?.bundle_choices || [])];
    [...(line?.metadata?.groups || []), ...(line?.metadata?.bundles || [])].forEach((stored) => {
      const group = allGroups.find((candidate) => candidate.id === stored.id);
      if (!group) return;
      const labels = (stored.selections || []).map((option) => option.label).filter(Boolean);
      selected[stored.id] = group.mode === 'multi' ? labels : (labels[0] || '');
    });
    const configuredLabels = new Set(allGroups.map((group) => `${group.label}:`));
    const freeNote = String(line?.note || '').split(' · ').filter((part) => !Array.from(configuredLabels).some((prefix) => part.startsWith(prefix))).join(' · ');
    return { selected, custom_note: freeNote, quantity: Math.max(1, num(line?.quantity, 1)) };
  }
  function openConfiguratorForLine(line) {
    const item = catalog.find((candidate) => String(candidate.id) === String(line.catalog_item_id));
    if (!item) return setLineEditor({ open: true, lineId: line.local_id });
    const profile = getProductProfile(item);
    setSelectedLineId(line.local_id);
    setConfigurator({ open: true, group: groupForCatalogItem(item), item, profile, selections: selectionsFromLine(line, profile), editLineId: line.local_id });
  }
  function lineSignature(line) {
    return JSON.stringify({ catalog_item_id: line.catalog_item_id, price: num(line.price), note: line.note || '', name: line.name || '', customer_display_name: line.customer_display_name || '' });
  }
  function addConfiguredItem(item, profile, selections) {
    const nextLine = buildConfiguredLine(item, profile, selections, () => crypto.randomUUID());
    if (configurator.editLineId) {
      setCart((prev) => prev.map((line) => line.local_id === configurator.editLineId ? recalcLine({ ...nextLine, local_id: line.local_id, manual_discount_amount: num(line.manual_discount_amount), promo_discount_amount: num(line.promo_discount_amount), discount_amount: num(line.discount_amount), applied_promo_code: line.applied_promo_code }) : line));
      setConfigurator({ open: false, group: null, item: null, profile: null, selections: null, editLineId: null });
      setNotice(`Updated ${nextLine.name}.`);
      return;
    }
    const signature = lineSignature(nextLine);
    setCart((prev) => {
      const existing = prev.find((line) => lineSignature(line) === signature);
      if (!existing) return [...prev, nextLine];
      return prev.map((line) => line.local_id === existing.local_id ? recalcLine({ ...line, quantity: num(line.quantity) + num(nextLine.quantity, 1) }) : line);
    });
    setConfigurator({ open: false, group: null, item: null, profile: null, selections: null, editLineId: null });
    setNotice(`Added ${item.display_name}.`);
  }
  async function setItemAvailability(item, isAvailable) {
    setError('');
    try {
      const updated = await updateCatalogItem(item.id, { is_available: isAvailable });
      setCatalog((prev) => prev.map((row) => row.id === item.id ? updated : row));
      setNotice(`${updated.display_name || updated.menu_item_name} marked ${isAvailable ? 'available' : 'sold out'}.`);
    } catch (e) {
      setError(e.message || 'Manager permission is required to update menu availability.');
    }
  }
  function updateLine(localId, patch) { setCart((prev) => prev.map((row) => row.local_id === localId ? recalcLine({ ...row, ...patch }) : row)); }
  function updateQty(localId, delta) { setCart((prev) => prev.map((row) => row.local_id === localId ? recalcLine({ ...row, quantity: Math.max(1, num(row.quantity) + delta) }) : row)); }
  function setQty(localId, qty) { updateLine(localId, { quantity: Math.max(1, num(qty, 1)) }); }
  function removeLine(localId) { setCart((prev) => prev.filter((row) => row.local_id !== localId)); if (selectedLineId === localId) setSelectedLineId(null); }
  function addPaymentRow() { setPayments((prev) => [...prev, emptyPayment('', '')]); setPaymentPad((prev) => ({ ...prev, paymentIndex: payments.length })); }
  function roomChargeFieldsForBooking(booking) {
    if (!booking) return {};
    return {
      room_charge_booking_snapshot_id: String(booking.id || ''),
      room_charge_booking_date: booking.stay_date || currentSession?.business_date || todayISO(),
      room_charge_service_date: currentSession?.business_date || todayISO(),
      room_charge_room_number: booking.room_number || '',
      room_charge_guest_label: booking.guest_label || booking.guest_name || '',
      room_charge_beds24_booking_id: booking.beds24_booking_id || '',
      room_charge_picker_query: `${booking.room_number || ''} ${booking.guest_label || booking.guest_name || ''}`.trim(),
    };
  }
  function chooseRoomServiceBooking(booking) {
    if (!booking) return;
    setActiveArea('Room Service');
    setOrderType('room_service');
    setTableLabel(booking.room_number || 'Room Service');
    setGuestName(booking.guest_label || booking.guest_name || '');
    setSeatCount('');
    setPayments((prev) => prev.map((row) => row.tender_type === 'room_charge' ? { ...row, ...roomChargeFieldsForBooking(booking), room_charge_order_source: 'room_service' } : row));
    setTerminalScreen('order');
    setNotice(`Room service order set for ${booking.room_number} · ${booking.guest_label || booking.guest_name || 'Guest'}.`);
  }
  function addRemainingTender(tenderType) {
    const remaining = Math.max(num(paymentSummary.remaining, 0), 0);
    const amount = remaining > 0 ? remaining : cartTotals.total;
    const nextIndex = payments.length;
    const roomBooking = tenderType === 'room_charge' ? currentRoomServiceBooking : null;
    setPayments((prev) => [...prev, {
      ...emptyPayment(amount, tenderType === 'cash' ? currentRegister?.accounting_financial_account_id || '' : ''),
      tender_type: tenderType,
      amount_received: tenderType === 'room_charge' ? '0' : String(amount),
      room_charge_booking_date: currentSession?.business_date || todayISO(),
      room_charge_service_date: currentSession?.business_date || todayISO(),
      room_charge_order_source: tenderType === 'room_charge' ? (orderType === 'room_service' ? 'room_service' : 'restaurant') : 'room_service',
      ...roomChargeFieldsForBooking(roomBooking),
    }]);
    setPaymentPad({ paymentIndex: nextIndex, target: tenderType === 'room_charge' ? 'amount_applied' : 'amount_received' });
  }
  function clearCart() {
    setCart([]); setGuestName(''); setTableLabel(''); setSeatCount(''); setOrderType(currentRegister?.default_order_type || 'dine_in'); setNote(''); setPayments([emptyPayment('', currentRegister?.accounting_financial_account_id || '')]); setCurrentOrderId(null); setCurrentOrderNo(''); setSelectedLineId(null); setDiscountApprovalUserId(null);
  }
  function beginOrderContext({ area = activeArea, label = '', pax = '', guest = '', type = 'dine_in' } = {}) {
    clearCart();
    setActiveArea(area);
    setTableLabel(label);
    setSeatCount(pax ? String(pax) : '');
    setGuestName(guest || '');
    setOrderType(type);
    setTerminalScreen('order');
  }
  function beginUnassignedDineInOrder() {
    const area = ['Room Service', 'Takeout'].includes(activeArea) ? 'Lobby' : activeArea;
    beginOrderContext({ area, label: '', pax: '', guest: '', type: 'dine_in' });
    setNotice('Add items now. Pay while the guest is present, or assign a table before holding/saving.');
  }
  function openAssignTablePrompt() {
    setAssignTablePrompt({
      open: true,
      targetTable: tableLabel || '',
      pax: seatCount || '',
      groupName: guestName || '',
    });
  }
  function closeAssignTablePrompt() {
    setAssignTablePrompt({ open: false, targetTable: '', pax: '', groupName: '' });
  }
  function assignSelectedTable() {
    setError('');
    const parsedTarget = parseTableValue(assignTablePrompt.targetTable);
    const targetTable = parsedTarget.code;
    const targetArea = parsedTarget.area;
    if (!targetTable) return setError('Choose a table before continuing.');
    const activeOrder = tableStatus[tableKey(targetArea, targetTable)] || tableStatus[targetTable];
    if (activeOrder && (!currentOrderId || String(activeOrder.id) !== String(currentOrderId))) {
      return setError('That table already has an active order. Choose an available table or merge from Spaces.');
    }
    const table = mapServiceTables.find((row) => row.area === targetArea && row.code === targetTable) || mapServiceTables.find((row) => row.code === targetTable);
    setActiveArea(targetArea || table?.area || activeArea);
    setTableLabel(targetTable);
    setSeatCount(assignTablePrompt.pax ? String(assignTablePrompt.pax) : '');
    setGuestName(assignTablePrompt.groupName || guestName || '');
    setOrderType('dine_in');
    closeAssignTablePrompt();
    setNotice(`Assigned order to ${targetTable}.`);
  }
  function ensureTableAssigned(actionLabel = 'continue') {
    if (!needsTableAssignment) return true;
    setPaymentOpen(false);
    setError(`Assign a table before ${actionLabel}.`);
    openAssignTablePrompt();
    return false;
  }
  function ensureTableBeforeLeaving(actionLabel = 'leaving this order') {
    if (!needsTableAssignment || !cart.length) return true;
    setPaymentOpen(false);
    setError(`Assign a table before ${actionLabel}, or take payment/clear the order while the guest is present.`);
    openAssignTablePrompt();
    return false;
  }
  function returnToSpaces() {
    setError('');
    if (!ensureTableBeforeLeaving('leaving this order')) return;
    setTerminalScreen('spaces');
  }
  function exitTerminal() {
    setError('');
    if (!ensureTableBeforeLeaving('exiting POS')) return;
    window.location.href = '/dashboard';
  }
  async function requestFullScreen() {
    if (typeof document === 'undefined') return;
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen?.();
        return;
      }
      await document.documentElement.requestFullscreen?.();
    } catch {
      setNotice('Full screen is not available in this browser. You can still use POS normally.');
    }
  }
  function openPaymentTerminal() {
    setError('');
    if (!cart.length) return setError('Add at least one item to the cart.');
    setPaymentOpen(true);
  }

  async function handleOpenSession(event) {
    event.preventDefault(); setError(''); setNotice('');
    try { await openRegisterSession({ ...openSessionForm, register_id: Number(openSessionForm.register_id), opening_float: num(openSessionForm.opening_float) }); setNotice('Register session opened.'); await loadAll({ silent: true }); } catch (e) { setError(e.message || 'Failed to open session.'); }
  }
  function buildOrderPayload() { return { register_session_id: Number(sessionId), approved_by_user_id: discountApprovalUserId || null, order_type: orderType, source_channel: 'pos', guest_name: guestName || null, service_area: activeArea || null, table_label: tableLabel || null, seat_count: seatCount ? Number(seatCount) : null, note: note || null, lines: cart.map((row) => ({ catalog_item_id: row.catalog_item_id, quantity: row.quantity, unit_price: row.price, discount_amount: num(row.discount_amount), note: row.note || null })) }; }
  function likelyConnectionError(err) {
    return !browserOnline || /failed to fetch|network|load failed|connection|offline|timeout/i.test(String(err?.message || ''));
  }
  function buildOfflineDraftSnapshot(reason = 'manual') {
    return {
      reason,
      register_session_id: sessionId || '',
      session_label: currentSession?.session_code || '',
      order_type: orderType,
      guest_name: guestName || '',
      table_label: tableLabel || '',
      seat_count: seatCount || '',
      active_area: activeArea,
      note: note || '',
      current_order_no: currentOrderNo || '',
      cart,
      payments,
      totals: cartTotals,
    };
  }
  function refreshOfflineDrafts() {
    setOfflineDrafts(listOfflineDrafts());
  }
  function saveCurrentOfflineDraft(reason = 'manual') {
    if (!cart.length) {
      setError('Add at least one item before saving an offline draft.');
      return null;
    }
    const draft = saveOfflineDraft(buildOfflineDraftSnapshot(reason));
    refreshOfflineDrafts();
    setNotice(`Offline emergency draft saved locally at ${new Date(draft.saved_at).toLocaleTimeString()}. Restore it when the POS connection is back.`);
    return draft;
  }
  function restoreOfflineDraft(draft) {
    if (!draft) return;
    setCart(Array.isArray(draft.cart) ? draft.cart : []);
    setPayments(Array.isArray(draft.payments) && draft.payments.length ? draft.payments : [emptyPayment('', currentRegister?.accounting_financial_account_id || '')]);
    setGuestName(draft.guest_name || '');
    setTableLabel(draft.table_label || '');
    setSeatCount(draft.seat_count || '');
    setActiveArea(draft.active_area || activeArea || 'Lobby');
    setOrderType(draft.order_type || currentRegister?.default_order_type || 'dine_in');
    setNote(draft.note || '');
    setCurrentOrderId(null);
    setCurrentOrderNo('');
    setSelectedLineId(null);
    setPaymentOpen(false);
    setTerminalScreen('order');
    setNotice('Offline draft restored. Review the cart, session, table, and tender before saving or taking payment.');
  }
  function deleteOfflineDraft(id) {
    removeOfflineDraft(id);
    refreshOfflineDrafts();
    setNotice('Offline draft removed from this device.');
  }
  async function saveOrUpdateOrder() {
    const payload = buildOrderPayload();
    if (currentOrderId) return updateOrder(currentOrderId, payload);
    const created = await createOrder(payload); setCurrentOrderId(created.id); setCurrentOrderNo(created.order_no); return created;
  }
  async function handleSaveDraft(status) {
    setError(''); setNotice('');
    if (!sessionId) return setError('Open or select a register session first.');
    if (!cart.length) return setError('Add at least one item to the cart.');
    if (!ensureTableAssigned(status === 'held' ? 'holding this dine-in order' : 'saving this dine-in order')) return;
    if (!browserOnline) {
      saveCurrentOfflineDraft(`offline-${status}`);
      return;
    }
    try { const order = await saveOrUpdateOrder(); if (status === 'held') { await holdOrder(order.id); setNotice(`Order ${order.order_no} held.`); } else setNotice(`Draft order ${order.order_no} saved.`); clearCart(); setTerminalScreen('spaces'); await loadAll({ silent: true }); } catch (e) { if (likelyConnectionError(e)) { saveCurrentOfflineDraft(`connection-failed-${status}`); return; } setError(e.message || 'Failed to save order.'); }
  }
  async function handlePay() {
    setError(''); setNotice('');
    if (!sessionId) return setError('Open or select a register session first.');
    if (!cart.length) return setError('Add at least one item to the cart.');
    const missingRoomChargeContext = payments.find((row) => row.tender_type === 'room_charge' && !String(row.room_charge_booking_snapshot_id || row.room_charge_room_number || row.room_charge_guest_label || '').trim());
    if (missingRoomChargeContext) return setError('Select a room or guest before completing a room charge.');
    if (!browserOnline) {
      saveCurrentOfflineDraft('payment-blocked-offline');
      return setError('POS connection is offline. The cart was saved locally, but payment and room-charge posting must wait until the server is reachable.');
    }
    if (Math.abs(totalApplied - cartTotals.total) > 0.01) return setError('Applied payment must equal cart total.');
    try {
      const order = await saveOrUpdateOrder();
      const settled = await payOrder(order.id, { payments: payments.map((row) => ({ tender_type: row.tender_type, amount_applied: num(row.amount_applied), amount_received: row.tender_type === 'room_charge' ? 0 : num(row.amount_received || row.amount_applied), reference_no: row.reference_no || null, accounting_financial_account_id: row.accounting_financial_account_id ? Number(row.accounting_financial_account_id) : null, room_charge_service_type: row.tender_type === 'room_charge' ? (row.room_charge_service_type || 'room_service') : null, room_charge_booking_date: row.tender_type === 'room_charge' ? (row.room_charge_booking_date || currentSession?.business_date || todayISO()) : null, room_charge_service_date: row.tender_type === 'room_charge' ? (row.room_charge_service_date || currentSession?.business_date || todayISO()) : null, room_charge_room_number: row.tender_type === 'room_charge' ? (row.room_charge_room_number || null) : null, room_charge_guest_label: row.tender_type === 'room_charge' ? (row.room_charge_guest_label || null) : null, room_charge_beds24_booking_id: row.tender_type === 'room_charge' ? (row.room_charge_beds24_booking_id || null) : null, room_charge_order_source: row.tender_type === 'room_charge' ? (row.room_charge_order_source || (orderType === 'room_service' ? 'room_service' : 'restaurant')) : null, room_charge_note: row.tender_type === 'room_charge' ? (row.room_charge_note || null) : null, room_charge_bill_to: row.tender_type === 'room_charge' ? (row.room_charge_bill_to || null) : null, room_charge_booking_snapshot_id: row.tender_type === 'room_charge' && row.room_charge_booking_snapshot_id ? Number(row.room_charge_booking_snapshot_id) : null })), note });
      setReceiptPreview(settled); saveLastReceipt(settled); setLastReceipt(settled); setPaymentOpen(false); setNotice(settled.status === 'folio_pending' ? `Order ${order.order_no} finalized to pending folio.` : `Order ${order.order_no} paid.`); clearCart(); setTerminalScreen('spaces'); await loadAll({ silent: true });
    } catch (e) { if (likelyConnectionError(e)) { saveCurrentOfflineDraft('payment-connection-failed'); return setError('Connection failed before payment could be confirmed. The cart was saved locally; verify Orders before taking payment again.'); } setError(e.message || 'Failed to pay order.'); }
  }
  function openQuickClose() {
    if (!currentSession?.id) return setError('Select an open session first.');
    setQuickClose({
      open: true,
      closing_actual_cash: String(currentSession.closing_expected_cash ?? currentSession.opening_float ?? ''),
      closing_note: '',
      variance_note: '',
      sign_off_name: '',
      sign_off_role: '',
      print_packet: true,
      manual_total: false,
      denominations: {},
    });
  }
  function setQuickCloseDenom(denom, qty) {
    setQuickClose((prev) => {
      const denominations = { ...(prev.denominations || {}), [denom]: qty };
      const total = CASH_DENOMS.reduce((sum, amount) => sum + (amount * num(denominations[amount], 0)), 0);
      return { ...prev, denominations, closing_actual_cash: String(total), manual_total: false };
    });
  }
  async function handleQuickClose() {
    setError(''); setNotice('');
    if (!currentSession?.id) return setError('Select an open session first.');
    if (!browserOnline) return setError('POS is offline. Do not close the drawer until the server connection is back.');
    const variance = num(quickClose.closing_actual_cash) - num(currentSession?.closing_expected_cash);
    if (Math.abs(variance) > 0.009 && !String(quickClose.variance_note || quickClose.closing_note || '').trim()) return setError('Enter a variance or close note before closing with a cash difference.');
    try {
      const closed = await closeRegisterSession(currentSession.id, {
        closing_actual_cash: num(quickClose.closing_actual_cash),
        closing_note: quickClose.closing_note || '',
        variance_note: quickClose.variance_note || '',
        sign_off_name: quickClose.sign_off_name || '',
        sign_off_role: quickClose.sign_off_role || '',
        close_mode: 'verified',
        blind_close: false,
        denomination_lines: CASH_DENOMS.map((amount, index) => ({
          line_label: String(amount),
          amount: amount * num(quickClose.denominations?.[amount], 0),
          notes: `qty=${num(quickClose.denominations?.[amount], 0)}`,
          sort_order: index,
        })).filter((line) => line.amount > 0),
      });
      setNotice(`Closed session ${currentSession.session_code}.`);
      setClosedSessionPacket(closed);
      if (quickClose.print_packet) printCloseSessionPacket(closed);
      setQuickClose({ open: false, closing_actual_cash: '', closing_note: '', variance_note: '', sign_off_name: '', sign_off_role: '', print_packet: true, manual_total: false, denominations: {} });
      clearCart();
      await loadAll({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to close session.');
    }
  }
  function openMoneyDrop() {
    if (!currentSession?.id) return setError('Select an open session first.');
    const safeAccount = findSafeDropAccount(accountingAccounts);
    setMoneyDrop({ open: true, amount: '', to_accounting_financial_account_id: safeAccount?.id ? String(safeAccount.id) : '', note: '', reference_no: '' });
  }
  async function handleMoneyDrop() {
    setError(''); setNotice('');
    if (!currentSession?.id) return setError('Select an open session first.');
    if (num(moneyDrop.amount, 0) <= 0) return setError('Money drop amount must be greater than zero.');
    if (!moneyDrop.to_accounting_financial_account_id) return setError('Select the safe or bank destination account for this money drop.');
    try {
      await createCashMovement({
        register_session_id: Number(currentSession.id),
        direction: 'out',
        movement_type: 'safe_drop',
        category: 'Safe Drop',
        amount: num(moneyDrop.amount),
        note: moneyDrop.note || null,
        reference_no: moneyDrop.reference_no || null,
        accounting_financial_account_id: currentSession.register_accounting_financial_account_id || currentRegister?.accounting_financial_account_id || null,
        to_accounting_financial_account_id: Number(moneyDrop.to_accounting_financial_account_id),
        requires_approval: true,
      });
      setNotice(`Money drop recorded: ${money(moneyDrop.amount)}.`);
      setMoneyDrop({ open: false, amount: '', to_accounting_financial_account_id: '', note: '', reference_no: '' });
      await loadAll({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to record money drop.');
    }
  }
  function openPaidOut() {
    if (!currentSession?.id) return setError('Select an open session first.');
    setPaidOut({ open: true, amount: '', category: 'Emergency Purchase', note: '', reference_no: '' });
  }
  async function handlePaidOut() {
    setError(''); setNotice('');
    if (!currentSession?.id) return setError('Select an open session first.');
    if (num(paidOut.amount, 0) <= 0) return setError('Paid out amount must be greater than zero.');
    try {
      await createCashMovement({
        register_session_id: Number(currentSession.id),
        direction: 'out',
        movement_type: 'paid_out',
        category: paidOut.category || 'Expense',
        amount: num(paidOut.amount),
        note: paidOut.note || null,
        reference_no: paidOut.reference_no || null,
        accounting_financial_account_id: currentSession.register_accounting_financial_account_id || currentRegister?.accounting_financial_account_id || null,
      });
      setNotice(`Paid out recorded: ${money(paidOut.amount)}.`);
      setPaidOut({ open: false, amount: '', category: 'Emergency Purchase', note: '', reference_no: '' });
      await loadAll({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to record paid out.');
    }
  }
  function selectServiceTable(table) {
    setMapEditor((prev) => ({ ...prev, selectedId: table.id }));
    if (mapEditor.editing) return;
    const activeOrder = tableStatus[tableValue(table)] || tableStatus[table.code];
    setTableAction({ open: true, mode: activeOrder ? 'occupied' : 'empty', table, order: activeOrder || null, groupName: activeOrder?.guest_name || '', pax: String(activeOrder?.seat_count || table.seats || ''), targetTable: '' });
  }
  function startServiceContext(area) {
    const type = area === 'Room Service' ? 'room_service' : area === 'Takeout' ? 'takeout' : 'dine_in';
    setTableAction({ open: true, mode: 'context', table: null, order: null, groupName: '', pax: '', targetTable: '', area, type });
  }
  function confirmTableAction() {
    if (tableAction.mode === 'empty') {
      beginOrderContext({ area: tableAction.table?.area || activeArea, label: tableAction.table?.code || '', pax: tableAction.pax, guest: tableAction.groupName, type: 'dine_in' });
    } else if (tableAction.mode === 'context') {
      beginOrderContext({ area: tableAction.area || activeArea, label: tableAction.area || '', pax: tableAction.pax, guest: tableAction.groupName, type: tableAction.type || 'dine_in' });
    }
    setTableAction({ open: false, mode: '', table: null, order: null, groupName: '', pax: '', targetTable: '' });
  }
  function openTableOrder(order) {
    if (!order) return;
    setTableAction((prev) => ({ ...prev, open: false }));
    loadOrderIntoCart(order, true);
  }
  async function stageTransfer(order, targetTable) {
    if (!order || !targetTable) return setError('Choose a target table first.');
    const target = parseTableValue(targetTable);
    setTableAction((prev) => ({ ...prev, open: false }));
    try {
      const transferred = await transferOrderTable(order.id, { target_service_area: target.area || null, target_table_label: target.code });
      loadOrderIntoCart(transferred, false);
      setTerminalScreen('order');
      setNotice(`Order transferred to ${[target.area, target.code].filter(Boolean).join(' · ')}.`);
      await loadAll({ silent: true });
    } catch (e) { setError(e.message || 'Failed to transfer table.'); }
  }
  async function stageMerge(order, targetTable) {
    if (!order || !targetTable) return setError('Choose a table/order to merge with first.');
    const target = parseTableValue(targetTable);
    setTableAction((prev) => ({ ...prev, open: false }));
    try {
      const merged = await mergeOrderTable(order.id, { target_service_area: target.area || null, target_table_label: target.code });
      loadOrderIntoCart(merged, false);
      setTerminalScreen('order');
      setNotice(`Orders merged into ${[target.area, target.code].filter(Boolean).join(' · ')}.`);
      await loadAll({ silent: true });
    } catch (e) { setError(e.message || 'Failed to merge tables.'); }
  }
  function addMapTable() {
    const id = `table-${Date.now()}`;
    const next = {
      id,
      kind: 'table',
      area: ['Room Service', 'Takeout'].includes(activeArea) ? 'Lobby' : activeArea,
      code: `${activeArea.slice(0, 2).toUpperCase()}${areaTables.length + 1}`,
      x: 50,
      y: 50,
      seats: 4,
      shape: activeArea === 'Pool' || activeArea === 'Garden' || activeArea === 'Terrace' ? 'umbrella' : 'round',
    };
    setTableLayout((prev) => ({ ...prev, tables: [...(prev.tables || []), next] }));
    setMapEditor((prev) => ({ ...prev, selectedId: id }));
  }
  function addMapElement(shape = 'rectangle') {
    const id = `element-${Date.now()}`;
    const next = {
      id,
      kind: 'element',
      area: ['Room Service', 'Takeout'].includes(activeArea) ? 'Lobby' : activeArea,
      code: shape === 'label' ? 'Label' : shape[0].toUpperCase() + shape.slice(1),
      x: 50,
      y: 50,
      w: shape === 'line' || shape === 'wall' || shape === 'path' ? 160 : 118,
      h: shape === 'line' || shape === 'wall' ? 14 : (shape === 'label' ? 34 : 68),
      shape,
      fill_color: shape === 'pool' ? '#bae6fd' : shape === 'plant' ? '#bbf7d0' : '#e5e7eb',
    };
    setTableLayout((prev) => ({ ...prev, tables: [...(prev.tables || []), next] }));
    setMapEditor((prev) => ({ ...prev, selectedId: id }));
  }
  function updateMapTable(id, patch) {
    setTableLayout((prev) => ({ ...prev, tables: (prev.tables || []).map((table) => table.id === id ? { ...table, ...patch } : table) }));
  }
  function deleteMapTable(id) {
    setTableLayout((prev) => ({ ...prev, tables: (prev.tables || []).filter((table) => table.id !== id) }));
    setMapEditor((prev) => ({ ...prev, selectedId: prev.selectedId === id ? '' : prev.selectedId }));
  }
  function updateDraggingTable(event) {
    if (!mapEditor.draggingId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.max(6, Math.min(94, ((event.clientX - rect.left) / rect.width) * 100));
    const y = Math.max(10, Math.min(90, ((event.clientY - rect.top) / rect.height) * 100));
    updateMapTable(mapEditor.draggingId, { x: Math.round(x), y: Math.round(y) });
  }
  async function saveMapLayout() {
    setError(''); setNotice('');
    const seenTables = new Set();
    for (const table of tableLayout.tables || []) {
      if (isMapVisualElement(table)) continue;
      const code = String(table.code || '').trim();
      const area = String(table.area || '').trim();
      if (!code) return setError('Every service table needs a table code before saving the map.');
      const key = `${area.toLowerCase()}::${code.toLowerCase()}`;
      if (seenTables.has(key)) return setError('A table with this code already exists in this area.');
      seenTables.add(key);
    }
    try {
      const saved = await updateTableLayout(tableLayout);
      setTableLayout({
        areas: Array.isArray(saved?.areas) ? saved.areas : tableLayout.areas,
        tables: Array.isArray(saved?.tables) ? saved.tables : tableLayout.tables,
      });
      setMapEditor({ editing: false, selectedId: '', draggingId: '' });
      setMapManagerOpen(false);
      setNotice('Table map saved.');
    } catch (e) {
      setError(e.message || 'Failed to save table map. Manager settings permission may be required.');
    }
  }
  function loadOrderIntoCart(order, shouldResume = true) {
    if (!order) return;
    const after = (nextOrder) => {
      const savedArea = nextOrder.service_area || mapServiceTables.find((table) => table.code === nextOrder.table_label)?.area || activeArea;
      setCurrentOrderId(nextOrder.id); setCurrentOrderNo(nextOrder.order_no || ''); setSessionId(String(nextOrder.register_session_id)); setActiveArea(savedArea || 'Lobby'); setGuestName(nextOrder.guest_name || ''); setTableLabel(nextOrder.table_label || ''); setSeatCount(nextOrder.seat_count || ''); setOrderType(nextOrder.order_type || 'dine_in'); setNote(nextOrder.note || '');
      setCart((nextOrder.lines || []).map((line) => recalcLine({ local_id: crypto.randomUUID(), catalog_item_id: line.catalog_item_id, name: line.item_name_snapshot, customer_display_name: line.item_name_snapshot, sku_code: line.sku_code, base_price: num(line.unit_price), price: num(line.unit_price), quantity: num(line.quantity), note: line.note || '', manual_discount_amount: num(line.discount_amount), promo_discount_amount: 0, discount_amount: num(line.discount_amount) })));
      setPayments((nextOrder.payment_breakdown || []).length ? (nextOrder.payment_breakdown || []).map((payment) => ({ tender_type: payment.tender_type, amount_applied: String(payment.amount_applied || ''), amount_received: String(payment.amount_received || payment.amount_applied || ''), reference_no: payment.reference_no || '', accounting_financial_account_id: String(payment.accounting_financial_account_id || ''), room_charge_service_type: payment.room_charge_posting?.service_type || 'room_service', room_charge_booking_date: payment.room_charge_posting?.booking_date || nextOrder.business_date || todayISO(), room_charge_service_date: payment.room_charge_posting?.service_date || nextOrder.business_date || todayISO(), room_charge_room_number: payment.room_charge_posting?.room_number || '', room_charge_guest_label: payment.room_charge_posting?.guest_label || '', room_charge_beds24_booking_id: payment.room_charge_posting?.beds24_booking_id || '', room_charge_order_source: payment.room_charge_posting?.order_source || (nextOrder.order_type === 'room_service' ? 'room_service' : 'restaurant'), room_charge_note: payment.room_charge_posting?.note || '', room_charge_bill_to: payment.room_charge_posting?.bill_to || '', room_charge_booking_snapshot_id: String(payment.room_charge_posting?.booking_snapshot_id || ''), room_charge_picker_query: `${payment.room_charge_posting?.room_number || ''} ${payment.room_charge_posting?.guest_label || ''}`.trim() })) : [emptyPayment(nextOrder.total_amount || '', currentRegister?.accounting_financial_account_id || '')]);
      setTerminalScreen('order'); setNotice(`Loaded ${nextOrder.order_no} into cart.`);
    };
    if (!shouldResume) return after(order);
    resumeOrder(order.id).then(after).catch((e) => setError(e.message || 'Failed to resume held order.'));
  }
  function addQuickAmount(amount) { setPayments((prev) => prev.map((row, idx) => idx === paymentPad.paymentIndex ? { ...row, amount_received: String(amount), amount_applied: row.amount_applied || String(cartTotals.total) } : row)); }
  function setPaymentField(index, key, value) { setPayments((prev) => prev.map((row, idx) => idx === index ? { ...row, [key]: value } : row)); }
  function applyRoomChargeBooking(index, snapshotId) {
    const booking = inHouseBookings.find((row) => String(row.id) === String(snapshotId));
    setPayments((prev) => prev.map((row, idx) => {
      if (idx !== index) return row;
      if (!booking) return { ...row, room_charge_booking_snapshot_id: '', room_charge_room_number: '', room_charge_guest_label: '', room_charge_beds24_booking_id: '' };
      return {
        ...row,
        room_charge_booking_snapshot_id: String(booking.id),
        room_charge_booking_date: booking.stay_date || row.room_charge_booking_date,
        room_charge_room_number: booking.room_number || '',
        room_charge_guest_label: booking.guest_label || booking.guest_name || '',
        room_charge_beds24_booking_id: booking.beds24_booking_id || '',
      };
    }));
  }
  function smartPickRoomChargeBooking(index) {
    const row = payments[index];
    const booking = pickRoomChargeBooking(inHouseBookings, {
      stayDate: row?.room_charge_booking_date || currentSession?.business_date || todayISO(),
      roomNumber: row?.room_charge_room_number || '',
      guestName: row?.room_charge_guest_label || '',
      query: row?.room_charge_picker_query || '',
    });
    if (!booking?.id) return setError('No close booking match found for this room charge.');
    applyRoomChargeBooking(index, booking.id);
    setNotice(`Matched room ${booking.room_number} for folio posting.`);
  }
  function applyPayPad(key) {
    setPayments((prev) => prev.map((row, idx) => {
      if (idx !== paymentPad.paymentIndex) return row;
      return { ...row, [paymentPad.target]: applyKeypadInput(row[paymentPad.target], key) };
    }));
  }
  function applyBarcode() {
    const query = barcode.trim().toLowerCase();
    if (!query) return;
    const item = catalog.find((row) => [row.sku_code, row.display_name, row.menu_item_name].some((v) => String(v || '').toLowerCase() === query));
    if (!item) return setError('No matching item found for barcode / code.');
    if (item.is_available === false) return setError(`${item.display_name || item.menu_item_name} is sold out.`);
    openConfiguratorForItem(item); setBarcode('');
  }
  function applySuggestedPromotion(promo) { setCart((prev) => applyPromotion(prev, promo)); setNotice(`Applied ${promo.label}.`); }
  function setManualDiscountForLine(line, nextDiscount) { requestDiscountApproval(nextDiscount, () => { setCart((prev) => prev.map((row) => row.local_id === line.local_id ? updateLineWithDiscount(row, nextDiscount) : row)); setNotice('Line discount updated.'); }); }
  function lineNoteWithTag(note, tag) {
    const clean = String(note || '').trim();
    return clean.includes(tag) ? clean : [clean, tag].filter(Boolean).join(' · ');
  }
  function lineNoteWithoutEligibilityTags(note) {
    return String(note || '').replace(/\s*·?\s*\[(Senior|PWD) 20%[^\]]*\]/g, '').trim();
  }
  function applyEligibilityDiscount(line, label) {
    const unitDiscount = Math.round(num(line.price) * 0.2 * 100) / 100;
    const cap = Math.round(lineGross(line) * 0.2 * 100) / 100;
    const nextDiscount = Math.min(cap, Math.round((num(line.manual_discount_amount) + unitDiscount) * 100) / 100);
    setCart((prev) => prev.map((row) => row.local_id === line.local_id ? updateLineWithDiscount({ ...row, note: lineNoteWithTag(row.note, `[${label} 20%]`) }, nextDiscount) : row));
    setNotice(`${label} 20% applied to one eligible dish.`);
  }
  function clearEligibilityDiscount(line) {
    setCart((prev) => prev.map((row) => row.local_id === line.local_id ? updateLineWithDiscount({ ...row, note: lineNoteWithoutEligibilityTags(row.note) }, 0) : row));
    setNotice('Line discount cleared.');
  }
  function renderOfflineDraftTools() {
    return (
      <div className="offline-draft-tools">
        <button type="button" className="secondary" onClick={() => saveCurrentOfflineDraft('manual-tool-save')} disabled={!cart.length}>
          Save Offline Draft
        </button>
        {!!offlineDrafts.length && (
          <details className="offline-drafts-list">
            <summary>Offline Drafts ({offlineDrafts.length})</summary>
            <div className="offline-drafts-panel">
              {offlineDrafts.slice(0, 6).map((draft) => (
                <div key={draft.id} className="offline-draft-row">
                  <button type="button" className="secondary" onClick={() => restoreOfflineDraft(draft)}>
                    <strong>{draft.table_label || draft.guest_name || 'Offline order'}</strong>
                    <span>{draft.cart?.length || 0} items · {money(draft.totals?.total || 0)} · {draft.saved_at ? new Date(draft.saved_at).toLocaleTimeString() : 'saved locally'}</span>
                  </button>
                  <button type="button" className="secondary" onClick={() => deleteOfflineDraft(draft.id)}>Remove</button>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    );
  }

  return (
    <div className="stack pos-page-root">
      {terminalScreen !== 'order' && (
      <section className="section pos-terminal-top">
        <div className="pos-compact-topbar">
          <div className="pos-brand-mini">
            <strong>POS</strong>
            <span>{terminalScreen === 'spaces' ? 'Spaces' : 'Order'}</span>
          </div>
          <label className="pos-session-compact">
            <span>Session</span>
            <select value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
              <option value="">Select session</option>
              {sessions.map((row) => (
                <option key={row.id} value={row.id}>{row.session_code} · {row.register_name}</option>
              ))}
            </select>
          </label>
          <span className={`badge ${currentSession ? 'success' : 'warn'}`}>
            {currentSession ? currentSession.session_code : 'No session'}
          </span>
          {currentOrderId && (
            <span className="badge info">Editing {currentOrderNo || `Order #${currentOrderId}`}</span>
          )}
          <span className={`badge ${browserOnline ? 'success' : 'warn'}`}>
            {browserOnline ? 'Online' : 'Offline draft mode'}
          </span>
          <span className={`badge ${terminalHealthSummary.tone}`}>{terminalHealthSummary.label}</span>
          {!!offlineDrafts.length && <span className="badge warn">{offlineDrafts.length} local drafts</span>}
          <Link href="/dashboard" className="terminal-exit-link">Exit POS</Link>
          <div className="pos-top-message">
            {!!error && <span className="error-text">{error}</span>}
            {!error && !!notice && <span className="notice-text">{notice}</span>}
            {!error && !notice && terminalHealthSummary.tone !== 'success' && <span className="notice-text">{terminalHealthSummary.detail}</span>}
          </div>
          <details className="pos-tools-menu">
            <summary>Tools</summary>
            <div className="pos-tools-panel">
              {currentSession && (
                <button type="button" className="secondary" onClick={openMoneyDrop}>Money Drop</button>
              )}
              {currentSession && (
                <button type="button" className="secondary" onClick={openPaidOut}>Paid Out / Expense</button>
              )}
              {currentSession && (
                <button type="button" className="secondary" onClick={openQuickClose}>Close Session</button>
              )}
              <button type="button" className="secondary" onClick={() => setAvailabilityOpen(true)}>Menu Availability</button>
              <button type="button" className="secondary" onClick={openMapManager}>Manage Service Map</button>
              <button type="button" className="secondary" onClick={openCustomerDisplay}>Customer Display</button>
              <button type="button" className="secondary" onClick={requestFullScreen}>Full Screen</button>
              {renderOfflineDraftTools()}
              {!!lastReceipt && (
                <button type="button" className="secondary" onClick={() => printReceipt(lastReceipt)}>Reprint Last Receipt</button>
              )}
            </div>
          </details>
        </div>
      </section>
      )}
      {!browserOnline && <section className="section offline-pos-warning"><div className="offline-warning-grid"><div><strong>{terminalHealthSummary.label}</strong><p className="small muted">{terminalHealthSummary.detail}</p><p className="small muted">{terminalHealthSummary.action}</p></div>{renderOfflineDraftTools()}</div></section>}
      {!sessions.length && <section className="section"><h2>Open a Session</h2><form className="form-grid" onSubmit={handleOpenSession} style={{ marginTop: 12 }}><label className="field">Register<select value={openSessionForm.register_id} onChange={(e) => setOpenSessionForm((prev) => ({ ...prev, register_id: e.target.value }))}><option value="">Select register</option>{registers.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label className="field">Business Date<input type="date" value={openSessionForm.business_date} onChange={(e) => setOpenSessionForm((prev) => ({ ...prev, business_date: e.target.value }))} /></label><label className="field">Shift Name<input value={openSessionForm.shift_name} onChange={(e) => setOpenSessionForm((prev) => ({ ...prev, shift_name: e.target.value }))} /></label><label className="field">Opening Float<input type="number" step="0.01" value={openSessionForm.opening_float} onChange={(e) => setOpenSessionForm((prev) => ({ ...prev, opening_float: e.target.value }))} /></label><label className="field" style={{ gridColumn: '1 / -1' }}>Note<textarea value={openSessionForm.opening_note} onChange={(e) => setOpenSessionForm((prev) => ({ ...prev, opening_note: e.target.value }))} /></label><div className="row"><button className="primary" type="submit">Open Session</button></div></form></section>}
      {sessions.length > 0 && terminalScreen === 'spaces' && (
        <section className="pos-redesign pos-spaces-screen">
          <div className="spaces-command-strip">
            <div className="spaces-area-tabs">{serviceAreas.map((area) => <button key={area} type="button" className={activeArea === area ? 'active' : ''} onClick={() => setActiveArea(area)}>{area}</button>)}</div>
            <button type="button" className="primary start-order-first-button" onClick={beginUnassignedDineInOrder}>Start Order First</button>
          </div>
          <div className="spaces-grid">
            <div className="spaces-map-panel">
              <div className="spaces-panel-head"><div><h2>{activeArea}</h2><p className="muted">Choose the service context before ordering.</p></div><span className="small muted">Map tools live under Tools</span></div>
              {['Room Service', 'Takeout'].includes(activeArea) ? (
                <div className="service-context-card">
                  <button type="button" className="service-context-main" onClick={() => startServiceContext(activeArea)}>{activeArea}</button>
                  <p className="muted">{activeArea === 'Room Service' ? 'Create a room-service order, then use room charge in payment when needed.' : 'Create a counter/pickup order without a physical table.'}</p>
                  {activeArea === 'Room Service' && (
                    <div className="row wrap" style={{ marginTop: 12 }}>
                      {inHouseBookings.map((booking) => (
                        <button key={booking.id} type="button" className="secondary" onClick={() => chooseRoomServiceBooking(booking)}>
                          {booking.room_number} · {booking.guest_label || booking.guest_name || 'Guest'}
                        </button>
                      ))}
                      {!inHouseBookings.length && <span className="small muted">No connected in-house bookings for this business date.</span>}
                    </div>
                  )}
                </div>
              ) : (
                <div className={`hotel-map-surface resort-map area-${activeArea.toLowerCase().replace(/\s+/g, '-')}`}>
                  {areaMapElements.map((element) => <div key={element.id || element.code} className={`map-visual-node ${element.shape || 'rectangle'}`} style={{ '--x': `${element.x}%`, '--y': `${element.y}%`, '--w': `${num(element.w, 118)}px`, '--h': `${num(element.h, 68)}px`, '--fill': element.fill_color || '#e5e7eb' }}><span>{element.code}</span></div>)}
                  {areaTables.map((table) => {
                    const activeOrder = tableStatus[tableValue(table)] || tableStatus[table.code];
                    return <button key={table.id || table.code} type="button" className={`hotel-table-node ${table.shape} ${activeOrder ? 'occupied' : ''} ${mapEditor.selectedId === table.id ? 'active' : ''}`} style={{ '--x': `${table.x}%`, '--y': `${table.y}%` }} onPointerDown={(e) => { if (!mapEditor.editing) return; e.preventDefault(); e.currentTarget.setPointerCapture?.(e.pointerId); setMapEditor((prev) => ({ ...prev, selectedId: table.id, draggingId: table.id })); }} onClick={() => selectServiceTable(table)}><span>{table.shape === 'umbrella' ? '☂ ' : ''}{table.code}</span><small>{activeOrder ? activeOrder.status : `${table.seats} pax`}</small></button>;
                  })}
                </div>
              )}
            </div>
            <aside className="spaces-queue-panel">
              <div className="spaces-panel-head"><div><h2>Service Queue</h2><p className="muted">Priority looks at stage, hold/unpaid state, and time.</p></div><button type="button" className="secondary" onClick={() => loadAll({ silent: true })}>Refresh</button></div>
              <div className="queue-tabs compact">{PRIMARY_QUEUE_VIEWS.map((view) => <button key={view} type="button" className={serviceQueueView === view ? 'active' : ''} onClick={() => setServiceQueueView(view)}>{QUEUE_VIEW_LABELS[view]}</button>)}<label className="queue-view-select"><span>View</span><select value={SECONDARY_QUEUE_VIEWS.includes(serviceQueueView) ? serviceQueueView : ''} onChange={(e) => e.target.value ? setServiceQueueView(e.target.value) : null}><option value="">More</option>{SECONDARY_QUEUE_VIEWS.map((view) => <option key={view} value={view}>{QUEUE_VIEW_LABELS[view]}</option>)}</select></label></div>
              <div className="queue-list">{serviceQueueItems.map((row) => <button key={`${row.kind}-${row.order?.id || row.table?.id || row.name}`} type="button" className={`queue-row priority-${row.urgency || 'normal'} ${row.kind === 'table' && row.status === 'empty' ? 'empty' : ''}`} onClick={() => row.order ? loadOrderIntoCart(row.order, true) : selectServiceTable(row.table)}><div><strong>{row.name}{row.guest ? ` · ${row.guest}` : ''}{row.pax ? ` · ${row.pax} pax` : ''}</strong><div className="small muted">{row.area} · {elapsedLabel(row.ageMinutes)} · {row.statusLabel || serviceLabel(row.status)}</div></div><div className="text-right"><span className={`badge ${row.status === 'empty' ? 'info' : row.status === 'held' ? 'warn' : row.unpaid ? 'warn' : 'success'}`}>{row.statusLabel || serviceLabel(row.status)}</span><div className="small muted">{row.unpaid ? `${money(row.unpaid)} unpaid` : row.kind === 'table' ? 'Ready' : ''}</div></div></button>)}{!serviceQueueItems.length && <p className="muted">No matching service items.</p>}</div>
            </aside>
          </div>
        </section>
      )}
      {sessions.length > 0 && terminalScreen === 'order' && (
        <section className="pos-redesign order-terminal-screen">
          <div className="order-topbar">
            <div className="order-nav-block">
              <button type="button" className="secondary" onClick={returnToSpaces}>Spaces</button>
              <button type="button" className="terminal-exit-link" onClick={exitTerminal}>Exit</button>
            </div>
            <div className="order-context"><strong>{tableLabel || (needsTableAssignment ? 'Unassigned Order' : ORDER_TYPE_LABELS[orderType]) || 'New Order'}</strong><span>{needsTableAssignment ? 'Pay now, or assign table before holding' : (ORDER_TYPE_LABELS[orderType] || orderType)}{!needsTableAssignment && guestName ? ` · ${guestName}` : ''}{!needsTableAssignment && seatCount ? ` · ${seatCount} pax` : ''}{currentOrderNo ? ` · ${currentOrderNo}` : ''}</span></div>
            <div className="order-status-strip">
              <span className={`badge ${currentSession ? 'success' : 'warn'}`}>{currentSession ? currentSession.session_code : 'No session'}</span>
              <span className={`badge ${browserOnline ? 'success' : 'warn'}`}>{browserOnline ? 'Online' : 'Offline draft'}</span>
              <span className={`badge ${terminalHealthSummary.tone}`}>{terminalHealthSummary.label}</span>
              {needsTableAssignment && <span className="badge warn">Needs table</span>}
              {!!offlineDrafts.length && <span className="badge warn">{offlineDrafts.length} drafts</span>}
            </div>
            <div className="order-primary-actions">
              {needsTableAssignment && <button type="button" className="secondary assign-table-button" onClick={openAssignTablePrompt}>Assign Table</button>}
              <button type="button" className="secondary" onClick={() => handleSaveDraft('held')}>Hold</button>
              <button type="button" className="primary" onClick={openPaymentTerminal}>Pay</button>
              <details className="pos-tools-menu order-more-menu">
                <summary>More</summary>
                <div className="pos-tools-panel">
                  <button type="button" className="secondary" onClick={() => currentOrderId ? setTableAction({ open: true, mode: 'occupied', table: { area: activeArea, code: tableLabel }, order: { id: currentOrderId, guest_name: guestName, seat_count: seatCount }, groupName: '', pax: seatCount, targetTable: '' }) : setNotice('Save or hold the order once before transferring it.')}>Transfer Order</button>
                  <button type="button" className="secondary" onClick={openAssignTablePrompt}>Assign / Change Table</button>
                  <button type="button" className="secondary" onClick={() => setNotice('Choose the target order from Spaces, then use Merge from its action sheet.')}>Merge Orders</button>
                  <button type="button" className="secondary" onClick={clearCart}>Clear Order</button>
                  <button type="button" className="secondary" onClick={() => setAvailabilityOpen(true)}>Menu Availability</button>
                  <button type="button" className="secondary" onClick={openCustomerDisplay}>Customer Display</button>
                  <button type="button" className="secondary" onClick={requestFullScreen}>Full Screen</button>
                  {renderOfflineDraftTools()}
                </div>
              </details>
            </div>
          </div>
          <div className="order-workspace">
            <nav className="order-category-rail">{categories.map((category) => <button key={category} type="button" className={selectedCategory === category ? 'active' : ''} onClick={() => setSelectedCategory(category)}>{category}</button>)}</nav>
            <main className="order-items-panel">
              <div className="order-search-row"><label className="field">Search<input ref={searchRef} placeholder="Search menu" value={search} onChange={(e) => setSearch(e.target.value)} /></label><label className="field pos-code-field">Code<input ref={barcodeRef} value={barcode} onChange={(e) => setBarcode(e.target.value)} onKeyDown={(e) => e.key === 'Enter' ? applyBarcode() : null} placeholder="Scan" /></label><button type="button" className="secondary" onClick={applyBarcode}>Add</button></div>
              <div className="order-item-grid">{productGroups.map((group, index) => <button key={group.key} type="button" className={`order-item-card ${index < 6 && search ? 'search-priority-card' : ''} ${group.photo_url ? 'has-photo' : 'no-photo'} ${!group.is_available ? 'sold-out' : ''}`} disabled={!group.is_available} onClick={() => chooseProductGroup(group)}>{!group.is_available && <span className="sold-out-ribbon">Sold Out</span>}{group.photo_url ? <img src={group.photo_url} alt="" loading="lazy" onError={(event) => { event.currentTarget.remove(); }} /> : <span className="item-photo-fallback">{String(group.label || '?').trim().slice(0, 1).toUpperCase()}</span>}<span className="item-card-body"><strong>{group.label}</strong><span className="item-card-meta"><b>{groupPriceLabel(group)}</b>{!group.is_available ? 'Sold out' : group.availableItems.length > 1 ? `${group.availableItems.length} choices` : group.has_options ? 'Customize' : 'Tap to add'}</span></span></button>)}{!productGroups.length && <div className="card muted">No active items in this category.</div>}</div>
            </main>
            <aside className="order-cart-panel">
              <div className={`cart-context-box ${needsTableAssignment ? 'needs-table' : ''}`}><strong>{tableLabel || (needsTableAssignment ? 'Assign table after items' : ORDER_TYPE_LABELS[orderType]) || 'Order'}</strong><span>{needsTableAssignment ? 'Required before hold, save, or leaving unpaid' : (guestName || 'Walk-in')}{!needsTableAssignment && seatCount ? ` · ${seatCount} pax` : ''}</span></div>
              <div className="cart-lines-box">{cart.map((line) => <button key={line.local_id} type="button" className="calm-cart-line" onClick={() => openConfiguratorForLine(line)}><div><div className="cart-line-main"><span className="cart-line-qty">{num(line.quantity)}x</span><strong>{line.name}</strong></div>{lineDetailParts(line).map((part) => <span key={part} className="cart-line-detail">{part}</span>)}{num(line.discount_amount) > 0 && <span className="cart-line-detail discount">Less {money(line.discount_amount)}</span>}</div><strong className="cart-line-total">{money(Math.max(lineGross(line) - num(line.discount_amount), 0))}</strong></button>)}{!cart.length && <p className="muted">Tap an item to configure and add it.</p>}</div>
              <div className="cart-total-box"><label className="field cart-note-field">Order Note<textarea rows="1" value={note} onChange={(e) => setNote(e.target.value)} /></label><div className="pos-summary-row"><span>Subtotal</span><strong>{money(cartTotals.subtotal)}</strong></div><div className="pos-summary-row"><span>Discount</span><strong>{money(cartTotals.discount)}</strong></div><div className="pos-summary-row pos-summary-total"><span>Total</span><strong>{money(cartTotals.total)}</strong></div>{needsTableAssignment && <button type="button" className="secondary pos-pay-button" onClick={openAssignTablePrompt}>Assign Table</button>}<button type="button" className="primary pos-pay-button" onClick={openPaymentTerminal}>Pay {money(cartTotals.total)}</button></div>
            </aside>
          </div>
        </section>
      )}
      {assignTablePrompt.open && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card modal-card-medium assign-table-modal"><div className="modal-header"><div><h2>Assign Table</h2><p className="muted">This dine-in order can be built first. Pay now if the guest is still here, or assign a table before holding, saving, or leaving it active.</p></div><button type="button" className="secondary" onClick={closeAssignTablePrompt}>Cancel</button></div><div className="modal-form stack-tight"><label className="field">Available Table<select value={assignTablePrompt.targetTable} onChange={(e) => setAssignTablePrompt((prev) => ({ ...prev, targetTable: e.target.value }))}><option value="">Choose table</option>{availableAssignmentTables.map((table) => <option key={table.id || tableValue(table)} value={tableValue(table)}>{table.area} · {table.code}{table.seats ? ` · ${table.seats} pax` : ''}</option>)}</select></label>{!availableAssignmentTables.length && <p className="error-text small">No available tables are configured. Add or free a table from Spaces first.</p>}<div className="pax-picker"><span className="small muted">Pax</span>{PAX_PRESETS.map((pax) => <button key={pax} type="button" className={String(assignTablePrompt.pax) === String(pax) ? 'active' : ''} onClick={() => setAssignTablePrompt((prev) => ({ ...prev, pax: String(pax) }))}>{pax}</button>)}</div><div className="form-grid"><label className="field">Guest Count<input type="number" min="0" value={assignTablePrompt.pax} onChange={(e) => setAssignTablePrompt((prev) => ({ ...prev, pax: e.target.value }))} /></label><label className="field">Group / Guest Name<input value={assignTablePrompt.groupName} onChange={(e) => setAssignTablePrompt((prev) => ({ ...prev, groupName: e.target.value }))} placeholder="Optional" /></label></div><div className="row wrap"><button type="button" className="primary" onClick={assignSelectedTable} disabled={!assignTablePrompt.targetTable}>Assign Table</button><button type="button" className="secondary" onClick={closeAssignTablePrompt}>Keep Ordering</button></div></div></div></div>}
      {availabilityOpen && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card modal-card-medium availability-modal"><div className="modal-header"><div><h2>Menu Availability</h2><p className="muted">Manager tool for sold-out items and variations.</p></div><button type="button" className="secondary" onClick={() => setAvailabilityOpen(false)}>Close</button></div><div className="modal-form stack-tight"><label className="field">Search menu<input value={availabilitySearch} onChange={(e) => setAvailabilitySearch(e.target.value)} placeholder="Item, category, or variation" /></label><div className="availability-list">{availabilityRows.map((item) => <div key={item.id} className={`availability-row ${item.is_available === false ? 'sold-out' : ''}`}><div><strong>{item.display_name || item.menu_item_name}</strong><div className="small muted">{item.category_name || 'Uncategorized'}{item.variant_name ? ` · ${item.variant_name}` : ''}</div></div><span className={`badge ${item.is_available === false ? 'warn' : 'success'}`}>{item.is_available === false ? 'Sold out' : 'Available'}</span><button type="button" className="secondary" onClick={() => setItemAvailability(item, item.is_available === false)}>{item.is_available === false ? 'Restore' : 'Mark sold out'}</button></div>)}{!availabilityRows.length && <p className="muted">No matching items.</p>}</div></div></div></div>}
      {mapManagerOpen && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card modal-card-wide map-manager-modal"><div className="modal-header"><div><h2>Service Area Map</h2><p className="muted">Manager layout editor for service tables plus visual-only area elements.</p></div><button type="button" className="secondary" onClick={() => { setMapManagerOpen(false); setMapEditor((prev) => ({ ...prev, editing: false, draggingId: '' })); }}>Close</button></div><div className="modal-form map-manager-body"><div className="spaces-area-tabs">{serviceAreas.filter((area) => !['Room Service', 'Takeout'].includes(area)).map((area) => <button key={area} type="button" className={activeArea === area ? 'active' : ''} onClick={() => setActiveArea(area)}>{area}</button>)}</div><div className={`hotel-map-surface map-manager-surface editing area-${activeArea.toLowerCase().replace(/\s+/g, '-')}`} onPointerMove={updateDraggingTable} onPointerUp={() => setMapEditor((prev) => ({ ...prev, draggingId: '' }))} onPointerLeave={() => setMapEditor((prev) => ({ ...prev, draggingId: '' }))}>{areaMapElements.map((element) => <button key={element.id || element.code} type="button" className={`map-visual-node editable ${element.shape || 'rectangle'} ${mapEditor.selectedId === element.id ? 'active' : ''}`} style={{ '--x': `${element.x}%`, '--y': `${element.y}%`, '--w': `${num(element.w, 118)}px`, '--h': `${num(element.h, 68)}px`, '--fill': element.fill_color || '#e5e7eb' }} onPointerDown={(e) => { e.preventDefault(); e.currentTarget.setPointerCapture?.(e.pointerId); setMapEditor((prev) => ({ ...prev, selectedId: element.id, draggingId: element.id })); }} onClick={() => setMapEditor((prev) => ({ ...prev, selectedId: element.id }))}><span>{element.code}</span></button>)}{areaTables.map((table) => <button key={table.id || table.code} type="button" className={`hotel-table-node ${table.shape} ${mapEditor.selectedId === table.id ? 'active' : ''}`} style={{ '--x': `${table.x}%`, '--y': `${table.y}%` }} onPointerDown={(e) => { e.preventDefault(); e.currentTarget.setPointerCapture?.(e.pointerId); setMapEditor((prev) => ({ ...prev, selectedId: table.id, draggingId: table.id })); }} onClick={() => setMapEditor((prev) => ({ ...prev, selectedId: table.id }))}><span>{table.shape === 'umbrella' ? '☂ ' : ''}{table.code}</span><small>{table.seats} pax</small></button>)}</div><div className="hotel-map-editor map-manager-fields"><div className="row wrap map-add-row"><button type="button" className="secondary" onClick={addMapTable}>Add Table</button>{MAP_ELEMENT_SHAPES.slice(0, 6).map((shape) => <button key={shape} type="button" className="secondary" onClick={() => addMapElement(shape)}>Add {shape}</button>)}<button type="button" className="primary" onClick={saveMapLayout}>Save Map</button></div>{selectedMapTable ? <div className="hotel-map-editor-fields map-detail-fields"><label className="field">Name / Label<input value={selectedMapTable.code || ''} onChange={(e) => updateMapTable(selectedMapTable.id, { code: e.target.value })} /></label><label className="field">Area<select value={selectedMapTable.area || activeArea} onChange={(e) => updateMapTable(selectedMapTable.id, { area: e.target.value })}>{serviceAreas.filter((area) => !['Room Service', 'Takeout'].includes(area)).map((area) => <option key={area} value={area}>{area}</option>)}</select></label><label className="field">Kind<select value={isMapVisualElement(selectedMapTable) ? 'element' : 'table'} onChange={(e) => updateMapTable(selectedMapTable.id, e.target.value === 'element' ? { kind: 'element', seats: 0, w: selectedMapTable.w || 118, h: selectedMapTable.h || 68, fill_color: selectedMapTable.fill_color || '#e5e7eb' } : { kind: 'table', seats: selectedMapTable.seats || 4 })}><option value="table">Service table</option><option value="element">Visual element</option></select></label>{isMapVisualElement(selectedMapTable) ? <><label className="field">Shape<select value={selectedMapTable.shape || 'rectangle'} onChange={(e) => updateMapTable(selectedMapTable.id, { shape: e.target.value })}>{MAP_ELEMENT_SHAPES.map((shape) => <option key={shape} value={shape}>{shape}</option>)}</select></label><label className="field">Fill<input type="color" value={selectedMapTable.fill_color || '#e5e7eb'} onChange={(e) => updateMapTable(selectedMapTable.id, { fill_color: e.target.value })} /></label><label className="field">Width<input type="number" min="24" value={selectedMapTable.w || 118} onChange={(e) => updateMapTable(selectedMapTable.id, { w: num(e.target.value, 118) })} /></label><label className="field">Height<input type="number" min="8" value={selectedMapTable.h || 68} onChange={(e) => updateMapTable(selectedMapTable.id, { h: num(e.target.value, 68) })} /></label><div className="map-color-swatches">{MAP_ELEMENT_COLORS.map((color) => <button key={color} type="button" style={{ '--swatch': color }} className={selectedMapTable.fill_color === color ? 'active' : ''} onClick={() => updateMapTable(selectedMapTable.id, { fill_color: color })} />)}</div></> : <><label className="field">Seats<input type="number" min="1" value={selectedMapTable.seats || 1} onChange={(e) => updateMapTable(selectedMapTable.id, { seats: num(e.target.value, 1) })} /></label><label className="field">Shape<select value={selectedMapTable.shape || 'round'} onChange={(e) => updateMapTable(selectedMapTable.id, { shape: e.target.value })}>{TABLE_SHAPES.map((shape) => <option key={shape} value={shape}>{shape}</option>)}</select></label></>}<button type="button" className="secondary" onClick={() => deleteMapTable(selectedMapTable.id)}>Delete</button></div> : <p className="small muted">Tap an element on the map to edit it.</p>}</div></div></div></div>}
      {tableAction.open && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card modal-card-medium table-action-modal"><div className="modal-header"><div><h2>{tableAction.mode === 'occupied' ? [tableAction.table?.area, tableAction.table?.code].filter(Boolean).join(' · ') : tableAction.area || tableAction.table?.code || 'Service Context'}</h2><p className="muted">{tableAction.mode === 'occupied' ? 'This table has an active order.' : 'Start a new group quickly.'}</p></div><button type="button" className="secondary" onClick={() => setTableAction({ open: false, mode: '', table: null, order: null, groupName: '', pax: '', targetTable: '' })}>Cancel</button></div>{tableAction.mode === 'occupied' ? <div className="modal-form stack-tight"><button type="button" className="primary table-open-primary" onClick={() => openTableOrder(tableAction.order)}>Open Order</button><div className="transfer-box"><label className="field">Table tools<select value={tableAction.targetTable} onChange={(e) => setTableAction((prev) => ({ ...prev, targetTable: e.target.value }))}><option value="">Choose table</option>{(tableLayout.tables || []).filter((table) => !isMapVisualElement(table) && tableValue(table) !== tableValue(tableAction.table)).map((table) => <option key={table.id || tableValue(table)} value={tableValue(table)}>{table.area} · {table.code}</option>)}</select></label><p className="small muted">Transfer moves this order to an empty table. Merge combines it into the active order at the target table.</p><div className="row wrap"><button type="button" className="secondary" onClick={() => stageTransfer(tableAction.order, tableAction.targetTable)}>Transfer Order</button><button type="button" className="secondary" onClick={() => stageMerge(tableAction.order, tableAction.targetTable)}>Merge Orders</button></div></div></div> : <div className="modal-form stack-tight"><div className="pax-picker"><span className="small muted">Pax</span>{PAX_PRESETS.map((pax) => <button key={pax} type="button" className={String(tableAction.pax) === String(pax) ? 'active' : ''} onClick={() => setTableAction((prev) => ({ ...prev, pax: String(pax) }))}>{pax}</button>)}</div><div className="form-grid"><label className="field">Guest Count<input type="number" min="0" value={tableAction.pax} onChange={(e) => setTableAction((prev) => ({ ...prev, pax: e.target.value }))} /></label><label className="field">Group / Guest Name<input value={tableAction.groupName} onChange={(e) => setTableAction((prev) => ({ ...prev, groupName: e.target.value }))} placeholder="Optional" /></label></div><div className="row wrap"><button type="button" className="primary" onClick={confirmTableAction}>Continue to Order</button><button type="button" className="secondary" onClick={() => setTableAction({ open: false, mode: '', table: null, order: null, groupName: '', pax: '', targetTable: '' })}>Cancel</button></div></div>}</div></div>}
      {lineEditor.open && selectedLine && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card"><div className="modal-header"><div><h2>{selectedLine.name}</h2><p className="muted">{selectedLine.note || 'Cart line'}</p></div><button type="button" className="secondary" onClick={() => setLineEditor({ open: false, lineId: '' })}>Close</button></div><div className="modal-form stack-tight"><div className="quantity-picker"><button type="button" onClick={() => updateQty(selectedLine.local_id, -1)}>−</button><strong>{selectedLine.quantity}</strong><button type="button" onClick={() => updateQty(selectedLine.local_id, 1)}>+</button></div><div className="form-grid"><label className="field">Quantity<input type="number" min="1" value={selectedLine.quantity} onChange={(e) => setQty(selectedLine.local_id, e.target.value)} /></label><label className="field">Line Discount<input type="number" step="0.01" value={selectedLine.manual_discount_amount || ''} onChange={(e) => setManualDiscountForLine(selectedLine, e.target.value)} /></label></div><div className="line-discount-actions"><button type="button" className="secondary" onClick={() => applyEligibilityDiscount(selectedLine, 'Senior')}>Senior 20% · 1 dish</button><button type="button" className="secondary" onClick={() => applyEligibilityDiscount(selectedLine, 'PWD')}>PWD 20% · 1 dish</button><button type="button" className="secondary" onClick={() => clearEligibilityDiscount(selectedLine)}>Clear discount</button></div><label className="field">Item Note<textarea value={selectedLine.note || ''} onChange={(e) => updateLine(selectedLine.local_id, { note: e.target.value })} /></label><div className="row wrap"><button type="button" className="secondary" onClick={() => { removeLine(selectedLine.local_id); setLineEditor({ open: false, lineId: '' }); }}>Remove Line</button><button type="button" className="primary" onClick={() => setLineEditor({ open: false, lineId: '' })}>Done</button></div></div></div></div>}
      {paymentOpen && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card modal-card-wide payment-terminal-modal"><div className="modal-header"><div><h2>Payment</h2><p className="muted">{tableLabel || ORDER_TYPE_LABELS[orderType]} · {money(cartTotals.total)}</p></div><button type="button" className="secondary" onClick={() => setPaymentOpen(false)}>Close</button></div><div className="modal-form stack-tight"><div className="cashier-display-grid"><div className="cashier-display-card"><div className="small muted">Due</div><div className="cashier-display-value">{money(cartTotals.total)}</div></div><div className="cashier-display-card"><div className="small muted">Applied</div><div className="cashier-display-value">{money(totalApplied)}</div></div><div className="cashier-display-card"><div className="small muted">Change</div><div className="cashier-display-value">{money(totalChange)}</div></div><div className="cashier-display-card"><div className="small muted">Folio Pending</div><div className="cashier-display-value">{money(folioApplied)}</div></div></div>{!paymentSummary.balanced && <div className="card warn"><strong>Payment Validation</strong><div className="small">Applied payments must equal {money(cartTotals.total)}.</div></div>}<div className="quick-tender-panel"><div><strong>Split Payment</strong><div className="small muted">Remaining: {money(paymentSummary.remaining > 0 ? paymentSummary.remaining : 0)}</div></div><div className="row wrap"><button type="button" className="secondary" onClick={() => addRemainingTender('cash')}>Cash remaining</button><button type="button" className="secondary" onClick={() => addRemainingTender('gcash')}>GCash remaining</button><button type="button" className="secondary" onClick={() => addRemainingTender('card')}>Card remaining</button><button type="button" className="secondary" onClick={() => addRemainingTender('room_charge')}>Room charge</button><button type="button" className="secondary" onClick={() => addQuickAmount(cartTotals.total)}>Exact cash</button></div></div>{payments.map((row, idx) => <div key={idx} className={`payment-row-card ${paymentPad.paymentIndex === idx ? 'active' : ''}`}><div className="form-grid-3"><label className="field">Tender<select value={row.tender_type} onChange={(e) => setPayments((prev) => prev.map((item, i) => i === idx ? { ...item, tender_type: e.target.value, accounting_financial_account_id: e.target.value === 'cash' ? String(currentRegister?.accounting_financial_account_id || '') : (e.target.value === 'room_charge' ? '' : item.accounting_financial_account_id), amount_received: e.target.value === 'room_charge' ? '0' : item.amount_received, room_charge_booking_date: item.room_charge_booking_date || currentSession?.business_date || todayISO(), room_charge_service_date: item.room_charge_service_date || currentSession?.business_date || todayISO(), room_charge_order_source: e.target.value === 'room_charge' ? (orderType === 'room_service' ? 'room_service' : 'restaurant') : item.room_charge_order_source } : item))}>{TENDERS.map((t) => <option key={t} value={t}>{TENDER_LABELS[t] || t}</option>)}</select></label><label className="field">Applied<input type="number" step="0.01" value={row.amount_applied} onFocus={() => setPaymentPad({ paymentIndex: idx, target: 'amount_applied' })} onChange={(e) => setPaymentField(idx, 'amount_applied', e.target.value)} /></label><label className="field">Received<input type="number" step="0.01" disabled={row.tender_type === 'room_charge'} value={row.amount_received} onFocus={() => setPaymentPad({ paymentIndex: idx, target: 'amount_received' })} onChange={(e) => setPaymentField(idx, 'amount_received', e.target.value)} /></label><label className="field">Reference<input value={row.reference_no} onChange={(e) => setPaymentField(idx, 'reference_no', e.target.value)} /></label><details className="tender-routing-details"><summary>Routing</summary><label className="field">Settlement Account<input value={row.accounting_financial_account_id || ''} disabled={row.tender_type === 'room_charge'} onChange={(e) => setPaymentField(idx, 'accounting_financial_account_id', e.target.value)} placeholder={row.tender_type === 'cash' ? String(currentRegister?.accounting_financial_account_id || '') : (TENDER_ACCOUNT_HINTS[row.tender_type] || 'Mapped account')} /></label></details>{payments.length > 1 && <button type="button" className="secondary" onClick={() => setPayments((prev) => prev.filter((_, i) => i !== idx))}>Remove</button>}</div>{row.tender_type === 'room_charge' && <div className="room-charge-compact"><div className="room-charge-search-row"><label className="field">Room or Guest<input value={row.room_charge_picker_query || ''} onChange={(e) => setPaymentField(idx, 'room_charge_picker_query', e.target.value)} placeholder="Room, guest, or booking" /></label><button type="button" className="secondary" onClick={() => smartPickRoomChargeBooking(idx)}>Best Match</button></div><div className="form-grid"><label className="field">Service Type<select value={row.room_charge_service_type || 'room_service'} onChange={(e) => setPaymentField(idx, 'room_charge_service_type', e.target.value)}>{ROOM_CHARGE_SERVICE_TYPES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><label className="field">Stay Date<input type="date" value={row.room_charge_booking_date || currentSession?.business_date || todayISO()} onChange={(e) => setPaymentField(idx, 'room_charge_booking_date', e.target.value)} /></label><label className="field">Room Number<input value={row.room_charge_room_number || ''} onChange={(e) => setPaymentField(idx, 'room_charge_room_number', e.target.value)} /></label><label className="field">Guest / Booking<input value={row.room_charge_guest_label || ''} onChange={(e) => setPaymentField(idx, 'room_charge_guest_label', e.target.value)} /></label><label className="field">In-House Booking<select value={row.room_charge_booking_snapshot_id || ''} onChange={(e) => applyRoomChargeBooking(idx, e.target.value)}><option value="">Manual / no snapshot</option>{inHouseBookings.map((booking) => <option key={booking.id} value={booking.id}>{booking.room_number} · {booking.guest_label || booking.guest_name || 'Guest'} · {booking.stay_date}</option>)}</select></label><label className="field">Bill To<input value={row.room_charge_bill_to || ''} onChange={(e) => setPaymentField(idx, 'room_charge_bill_to', e.target.value)} /></label></div><div className="row wrap room-charge-matches">{getRoomChargeMatches(row).slice(0, 3).map((booking) => <button key={booking.id} type="button" className="secondary" onClick={() => applyRoomChargeBooking(idx, booking.id)}>{booking.room_number} · {booking.guest_label || booking.guest_name || 'Guest'}</button>)}</div><label className="field">Room Charge Note<textarea value={row.room_charge_note || ''} onChange={(e) => setPaymentField(idx, 'room_charge_note', e.target.value)} /></label></div>}</div>)}<div className="paypad-block"><div className="row" style={{ justifyContent: 'space-between' }}><span className="small muted">Active tender {paymentPad.paymentIndex + 1}: {paymentPad.target}</span><div className="segmented"><button type="button" className={`toggle-btn ${paymentPad.target === 'amount_received' ? 'on' : ''}`} onClick={() => setPaymentPad((prev) => ({ ...prev, target: 'amount_received' }))}>Received</button><button type="button" className={`toggle-btn ${paymentPad.target === 'amount_applied' ? 'on' : ''}`} onClick={() => setPaymentPad((prev) => ({ ...prev, target: 'amount_applied' }))}>Applied</button></div></div><div className="paypad-grid">{PAYPAD.map((key) => <button key={key} type="button" className="secondary paypad-key" onClick={() => applyPayPad(key)}>{key}</button>)}<button type="button" className="secondary paypad-key" onClick={() => applyPayPad('backspace')}>⌫</button><button type="button" className="secondary paypad-key" onClick={() => applyPayPad('clear')}>Clear</button></div></div><div className="row wrap"><button type="button" className="secondary" onClick={addPaymentRow}>Add blank tender</button><button type="button" className="secondary" onClick={() => handleSaveDraft('draft')}>Save Draft</button><button type="button" className="secondary" onClick={() => handleSaveDraft('held')}>Hold Order</button><button type="button" className="primary pos-pay-button" onClick={handlePay}>{folioApplied > 0 ? 'Finalize / Send to Folio' : 'Pay Now'}</button></div></div></div></div>}
      {!!receiptPreview && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card"><div className="modal-header"><div><h2>Receipt Preview</h2><p className="muted">{receiptPreview.order_no} · {receiptPreview.business_date}</p></div><button type="button" className="secondary" onClick={() => setReceiptPreview(null)}>Close</button></div><div className="modal-form stack-tight"><div className="small muted">{receiptPreview.guest_name || 'Walk-in'} · {receiptPreview.table_label || receiptPreview.order_type}</div>{(receiptPreview.lines || []).map((line) => <div key={line.id} className="list-row"><div>{line.item_name_snapshot} × {line.quantity}{line.note ? ` · ${line.note}` : ''}</div><div>{money(line.line_total)}</div></div>)}<div className="pos-summary-row"><span>Total</span><strong>{money(receiptPreview.total_amount)}</strong></div><div className="row wrap"><button type="button" className="primary" onClick={() => printReceipt(receiptPreview)}>Print Receipt</button>{!!lastReceipt && <button type="button" className="secondary" onClick={() => printReceipt(lastReceipt)}>Reprint Last</button>}</div></div></div></div>}
      {!!closedSessionPacket && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card"><div className="modal-header"><div><h2>Shift Close Packet</h2><p className="muted">{closedSessionPacket.session_code} · {closedSessionPacket.business_date}</p></div><button type="button" className="secondary" onClick={() => setClosedSessionPacket(null)}>Close</button></div><div className="modal-form stack-tight"><div className="cash-close-summary"><div className="cashier-display-card"><div className="small muted">Expected</div><div className="cashier-display-value">{money(closedSessionPacket.closing_expected_cash)}</div></div><div className="cashier-display-card"><div className="small muted">Counted</div><div className="cashier-display-value">{money(closedSessionPacket.closing_actual_cash)}</div></div><div className={`cashier-display-card ${Math.abs(num(closedSessionPacket.variance_amount)) > 0.009 ? 'warn' : 'success'}`}><div className="small muted">Variance</div><div className="cashier-display-value">{money(closedSessionPacket.variance_amount)}</div></div></div><p className="small muted">Keep this with the cash count, drops, paid-out receipts, and manager handover notes.</p><div className="row wrap"><button type="button" className="primary" onClick={() => printCloseSessionPacket(closedSessionPacket)}>Print Close Packet</button><button type="button" className="secondary" onClick={() => setClosedSessionPacket(null)}>Done</button></div></div></div></div>}
      {variantPicker.open && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card modal-card-medium pos-config-modal"><div className="modal-header"><div><h2>{variantPicker.label}</h2></div><button type="button" className="secondary" onClick={() => setVariantPicker({ open: false, label: '', items: [], action: 'order' })}>Close</button></div><div className="modal-form"><div className="pos-config-options">{variantPicker.items.map((item) => <button key={item.id} type="button" className="stat-chip pos-config-option" onClick={() => { setVariantPicker({ open: false, label: '', items: [], action: 'order' }); openConfiguratorForItem(item); }}>{getVariantLabel(item)}</button>)}</div></div></div></div>}
      {moneyDrop.open && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card"><div className="modal-header"><div><h2>Money Drop</h2><p className="muted">{currentSession?.session_code}</p></div><button type="button" className="secondary" onClick={() => setMoneyDrop({ open: false, amount: '', to_accounting_financial_account_id: '', note: '', reference_no: '' })}>Cancel</button></div><div className="modal-form stack-tight"><div className="form-grid"><label className="field">Amount<input type="number" step="0.01" min="0" value={moneyDrop.amount} onChange={(e) => setMoneyDrop((prev) => ({ ...prev, amount: e.target.value }))} /></label><label className="field">Safe / Bank Account<select value={moneyDrop.to_accounting_financial_account_id} onChange={(e) => setMoneyDrop((prev) => ({ ...prev, to_accounting_financial_account_id: e.target.value }))}><option value="">Select destination</option>{accountingAccounts.map((row) => <option key={row.id} value={row.id}>{row.name || row.account_name || `Account ${row.id}`}</option>)}</select></label><label className="field">Envelope / Reference<input value={moneyDrop.reference_no} onChange={(e) => setMoneyDrop((prev) => ({ ...prev, reference_no: e.target.value }))} placeholder="Drop bag or envelope no." /></label></div><label className="field">Note<textarea value={moneyDrop.note} onChange={(e) => setMoneyDrop((prev) => ({ ...prev, note: e.target.value }))} placeholder="Counted by / received by." /></label><div className="row wrap"><button type="button" className="primary" onClick={handleMoneyDrop}>Save Money Drop</button><button type="button" className="secondary" onClick={() => setMoneyDrop({ open: false, amount: '', to_accounting_financial_account_id: '', note: '', reference_no: '' })}>Cancel</button></div></div></div></div>}
      {paidOut.open && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card"><div className="modal-header"><div><h2>Paid Out / Expense</h2><p className="muted">{currentSession?.session_code}</p></div><button type="button" className="secondary" onClick={() => setPaidOut({ open: false, amount: '', category: 'Emergency Purchase', note: '', reference_no: '' })}>Cancel</button></div><div className="modal-form stack-tight"><div className="form-grid"><label className="field">Amount<input type="number" step="0.01" min="0" value={paidOut.amount} onChange={(e) => setPaidOut((prev) => ({ ...prev, amount: e.target.value }))} /></label><label className="field">Category<select value={paidOut.category} onChange={(e) => setPaidOut((prev) => ({ ...prev, category: e.target.value }))}><option value="Emergency Purchase">Emergency Purchase</option><option value="Cafe Supplies">Cafe Supplies</option><option value="Kitchen Supplies">Kitchen Supplies</option><option value="Transportation">Transportation</option><option value="Maintenance">Maintenance</option><option value="Other Expense">Other Expense</option></select></label><label className="field">Reference No<input value={paidOut.reference_no} onChange={(e) => setPaidOut((prev) => ({ ...prev, reference_no: e.target.value }))} placeholder="Receipt no." /></label></div><label className="field">Note<textarea value={paidOut.note} onChange={(e) => setPaidOut((prev) => ({ ...prev, note: e.target.value }))} placeholder="What was bought and who approved it." /></label><div className="row wrap"><button type="button" className="primary" onClick={handlePaidOut}>Save Paid Out</button><button type="button" className="secondary" onClick={() => setPaidOut({ open: false, amount: '', category: 'Emergency Purchase', note: '', reference_no: '' })}>Cancel</button></div></div></div></div>}
      {quickClose.open && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card modal-card-medium"><div className="modal-header"><div><h2>Close Session</h2><p className="muted">{currentSession?.session_code}</p></div><button type="button" className="secondary" onClick={() => setQuickClose({ open: false, closing_actual_cash: '', closing_note: '', variance_note: '', sign_off_name: '', sign_off_role: '', print_packet: true, manual_total: false, denominations: {} })}>Cancel</button></div><div className="modal-form stack-tight"><div className="cash-close-summary"><div className="cashier-display-card"><div className="small muted">Expected</div><div className="cashier-display-value">{money(currentSession?.closing_expected_cash)}</div></div><div className="cashier-display-card"><div className="small muted">Counted</div><div className="cashier-display-value">{money(quickClose.closing_actual_cash)}</div></div><div className={`cashier-display-card ${Math.abs(num(quickClose.closing_actual_cash) - num(currentSession?.closing_expected_cash)) > 0.009 ? 'warn' : 'success'}`}><div className="small muted">Variance</div><div className="cashier-display-value">{money(num(quickClose.closing_actual_cash) - num(currentSession?.closing_expected_cash))}</div></div></div><div className="cash-denom-grid">{CASH_DENOMS.map((amount) => <label key={amount} className="field cash-denom-field"><span>{money(amount)}</span><input type="number" min="0" inputMode="numeric" placeholder="0" value={quickClose.denominations?.[amount] || ''} onChange={(e) => setQuickCloseDenom(amount, e.target.value)} /></label>)}</div><label className="field-inline"><input type="checkbox" checked={!!quickClose.manual_total} onChange={(e) => setQuickClose((prev) => ({ ...prev, manual_total: e.target.checked }))} /> Use manual counted total</label>{quickClose.manual_total && <label className="field">Manual Counted Cash<input type="number" step="0.01" value={quickClose.closing_actual_cash} onChange={(e) => setQuickClose((prev) => ({ ...prev, closing_actual_cash: e.target.value }))} /></label>}<div className="form-grid"><label className="field">Variance Note<textarea value={quickClose.variance_note} onChange={(e) => setQuickClose((prev) => ({ ...prev, variance_note: e.target.value }))} placeholder="Required if counted cash is short or over." /></label><label className="field">Close Note<textarea value={quickClose.closing_note} onChange={(e) => setQuickClose((prev) => ({ ...prev, closing_note: e.target.value }))} placeholder="End-of-shift notes, handover, or investigation context." /></label><label className="field">Sign-off Name<input value={quickClose.sign_off_name} onChange={(e) => setQuickClose((prev) => ({ ...prev, sign_off_name: e.target.value }))} placeholder="Cashier or manager name" /></label><label className="field">Sign-off Role<input value={quickClose.sign_off_role} onChange={(e) => setQuickClose((prev) => ({ ...prev, sign_off_role: e.target.value }))} placeholder="Cashier / Manager" /></label></div><label className="field-inline"><input type="checkbox" checked={!!quickClose.print_packet} onChange={(e) => setQuickClose((prev) => ({ ...prev, print_packet: e.target.checked }))} /> Print close packet after closing</label><div className="row wrap"><button type="button" className="primary" onClick={handleQuickClose}>Close Session</button><button type="button" className="secondary" onClick={() => setQuickClose({ open: false, closing_actual_cash: '', closing_note: '', variance_note: '', sign_off_name: '', sign_off_role: '', print_packet: true, manual_total: false, denominations: {} })}>Cancel</button></div></div></div></div>}
      {configurator.open && configurator.item && configurator.profile && configurator.selections && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal-card modal-card-medium pos-config-modal"><div className="modal-header"><div><h2>{configurator.group?.label || configurator.item.menu_item_name || configurator.item.display_name}</h2><p className="muted">{money(configurator.item.price)} base</p></div><button type="button" className="secondary" onClick={() => setConfigurator({ open: false, group: null, item: null, profile: null, selections: null })}>Close</button></div><div className="modal-form stack-tight"><div className="pos-config-hero">{itemPhotoUrl(configurator.item) ? <img src={itemPhotoUrl(configurator.item)} alt="" onError={(event) => { event.currentTarget.remove(); }} /> : <span>{String(configurator.item.display_name || configurator.item.menu_item_name || '?').slice(0, 1).toUpperCase()}</span>}<div><strong>{configurator.item.display_name || configurator.item.menu_item_name}</strong><p className="muted">{(configurator.group?.items || []).length > 1 ? 'Choose the variation first, then add modifiers.' : selectedConfigGroups.length ? 'Customize only what the guest asks for.' : 'Simple item. Choose quantity and add.'}</p></div></div>{(configurator.group?.items || []).length > 1 && <div className="pos-config-group"><div className="row" style={{ justifyContent: 'space-between' }}><strong>Variation</strong><span className="small muted">Choose one</span></div><div className="pos-config-options">{configurator.group.items.map((item) => <button key={item.id} type="button" className={`stat-chip pos-config-option ${String(item.id) === String(configurator.item.id) ? 'active' : ''}`} onClick={() => { const profile = getProductProfile(item); setConfigurator((prev) => ({ ...prev, item, profile, selections: createDefaultSelections(profile) })); }}>{getVariantLabel(item)} · {money(item.price)}</button>)}</div></div>}{selectedConfigGroups.map((group) => <div className="pos-config-group" key={group.id}><div className="row" style={{ justifyContent: 'space-between' }}><strong>{group.label}</strong><span className="small muted">{group.required ? 'Required' : 'Optional'} · {group.mode === 'multi' ? 'Choose any' : 'Choose one'}</span></div><div className="pos-config-options">{(group.options || []).map((option) => { const current = configurator.selections.selected[group.id]; const selected = group.mode === 'multi' ? (Array.isArray(current) && current.includes(option.label)) : current === option.label; return <button key={option.label} type="button" className={`stat-chip pos-config-option ${selected ? 'active' : ''}`} onClick={() => setConfigurator((prev) => { const currentSelected = prev.selections.selected[group.id]; let nextValue = option.label; if (group.mode === 'multi') { const nextSet = new Set(Array.isArray(currentSelected) ? currentSelected : []); if (nextSet.has(option.label)) nextSet.delete(option.label); else nextSet.add(option.label); nextValue = Array.from(nextSet); } return { ...prev, selections: { ...prev.selections, selected: { ...prev.selections.selected, [group.id]: nextValue } } }; })}>{option.label}{num(option.price_delta) ? ` · +${money(option.price_delta)}` : ''}</button>; })}</div></div>)}<div className="quantity-section"><span>Quantity</span><div className="quantity-picker"><button type="button" onClick={() => setConfigurator((prev) => ({ ...prev, selections: { ...prev.selections, quantity: Math.max(1, num(prev.selections.quantity, 1) - 1) } }))}>−</button><strong>{configurator.selections.quantity}</strong><button type="button" onClick={() => setConfigurator((prev) => ({ ...prev, selections: { ...prev.selections, quantity: num(prev.selections.quantity, 1) + 1 } }))}>+</button></div></div><label className="field">{configurator.profile.prompt_note_label || 'Special Request'}<input value={configurator.selections.custom_note} onChange={(e) => setConfigurator((prev) => ({ ...prev, selections: { ...prev.selections, custom_note: e.target.value } }))} placeholder="Optional note" /></label>{configurator.editLineId && selectedLine && <div className="pos-config-group line-discount-panel"><div className="row" style={{ justifyContent: "space-between" }}><strong>Line discount</strong><span className="small muted">Senior/PWD or manager discount</span></div><label className="field">Manual Discount<input type="number" step="0.01" value={selectedLine.manual_discount_amount || ""} onChange={(e) => setManualDiscountForLine(selectedLine, e.target.value)} /></label><div className="line-discount-actions"><button type="button" className="secondary" onClick={() => applyEligibilityDiscount(selectedLine, "Senior")}>Senior 20% · 1 dish</button><button type="button" className="secondary" onClick={() => applyEligibilityDiscount(selectedLine, "PWD")}>PWD 20% · 1 dish</button><button type="button" className="secondary" onClick={() => clearEligibilityDiscount(selectedLine)}>Clear discount</button></div></div>}<div className="configurator-footer"><strong>{money(configuratorTotal)}</strong><button type="button" className="primary pos-config-add" onClick={() => addConfiguredItem(configurator.item, configurator.profile, configurator.selections)}>{configurator.editLineId ? "Update Line" : "Add to Order"}</button></div></div></div></div>}
      <ManagerOverrideModal open={overrideModal.open} title={overrideModal.title} subtitle={overrideModal.subtitle} actionLabel="Approve Override" onApprove={handleOverrideApproved} onClose={() => setOverrideModal({ open: false, title: '', subtitle: '' })} />
    </div>
  );
}
