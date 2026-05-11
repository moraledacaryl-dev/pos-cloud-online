import { useMemo } from 'react';

export function useGroupedKitchenTickets(tickets) {
  return useMemo(() => {
    const map = new Map();
    tickets.forEach((row) => {
      const key = row.order_no || String(row.order_id);
      const existing = map.get(key) || {
        key,
        order_id: row.order_id,
        order_no: row.order_no,
        table_label: row.table_label,
        guest_name: row.guest_name,
        order_type: row.order_type,
        priority: row.priority || 'normal',
        age_minutes: row.age_minutes || 0,
        lines: [],
      };
      existing.lines.push(row);
      if ((row.age_minutes || 0) > (existing.age_minutes || 0)) existing.age_minutes = row.age_minutes || 0;
      if (row.priority === 'critical' || (existing.priority !== 'critical' && row.priority === 'rush') || (!['critical', 'rush'].includes(existing.priority) && row.priority === 'watch')) {
        existing.priority = row.priority;
      }
      map.set(key, existing);
    });
    return Array.from(map.values()).sort((a, b) => {
      const aScore = a.priority === 'critical' ? -2 : a.priority === 'rush' ? -1 : a.priority === 'watch' ? 0 : 1;
      const bScore = b.priority === 'critical' ? -2 : b.priority === 'rush' ? -1 : b.priority === 'watch' ? 0 : 1;
      if (aScore !== bScore) return aScore - bScore;
      return (b.age_minutes || 0) - (a.age_minutes || 0);
    });
  }, [tickets]);
}

export function badgeClass(priority) {
  if (priority === 'critical') return 'danger';
  if (priority === 'rush') return 'danger';
  if (priority === 'watch') return 'warn';
  return 'info';
}

export function statusBadgeClass(status) {
  if (status === 'held') return 'warn';
  if (status === 'ready' || status === 'served') return 'success';
  if (status === 'in_progress') return 'warn';
  if (status === 'acknowledged') return 'info';
  if (status === 'queued') return 'secondary';
  return 'muted';
}

export function kitchenStatusLabel(status) {
  if (status === 'held') return 'Held';
  if (status === 'queued' || status === 'acknowledged') return 'New';
  if (status === 'in_progress') return 'Started';
  if (status === 'ready') return 'Ready';
  if (status === 'served') return 'Served';
  return status || 'New';
}

export function sourceLabel(ticket) {
  const labels = {
    dine_in: 'Dine-in',
    takeout: 'Takeout',
    room_service: 'Room Service',
    room_charge: 'Room Charge',
    delivery: 'Delivery',
  };
  if (ticket.order_type) return labels[ticket.order_type] || String(ticket.order_type).replace(/_/g, ' ');
  if (ticket.table_label && ticket.table_label.toLowerCase().includes('room')) return 'Room Charge';
  if (ticket.table_label) return ticket.table_label;
  return 'POS Order';
}
