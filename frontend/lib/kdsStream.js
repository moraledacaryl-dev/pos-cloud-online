import { API_BASE, request } from './api';

const DEVICE_STORAGE_KEY = 'pos_kds_device_id';

function randomDeviceId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `kds-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getKdsDeviceId() {
  if (typeof window === 'undefined') return '';
  let value = localStorage.getItem(DEVICE_STORAGE_KEY) || '';
  if (!value) {
    value = randomDeviceId();
    localStorage.setItem(DEVICE_STORAGE_KEY, value);
  }
  return value;
}

export async function createKitchenStreamTicket(station) {
  return request('/kitchen/stream-ticket', {
    method: 'POST',
    body: JSON.stringify({ station: station || null, device_id: getKdsDeviceId() || null }),
  });
}

export function kitchenStreamUrl(station, ticket) {
  const base = API_BASE.startsWith('http') ? API_BASE : `${window.location.origin}${API_BASE}`;
  const url = new URL(`${base}/kitchen/stream`);
  if (station) url.searchParams.set('station', station);
  url.searchParams.set('ticket', ticket);
  return url.toString();
}
