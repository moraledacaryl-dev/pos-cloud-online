'use client';

import { canAccess } from './permissions';

export const ROUTE_ITEMS = [
  { href: '/dashboard', label: 'Dashboard', title: 'Dashboard', subtitle: 'Live sales, sessions, drawer, and sync snapshot', permissionsAny: ['dashboard.view'], group: 'Main' },
  { href: '/pos', label: 'POS', title: 'POS Terminal', subtitle: 'Order taking, split payments, and cashier flow', permissionsAny: ['pos.use'], group: 'Main' },
  { href: '/kitchen', label: 'Kitchen', title: 'Kitchen', subtitle: 'One KDS for active work, held items, ready orders, stations, and all-day totals', permissionsAny: ['kitchen.view'], group: 'Main' },
  { href: '/kitchen-board', label: 'Kitchen Board', title: 'Kitchen', subtitle: 'One KDS for active work, held items, ready orders, stations, and all-day totals', permissionsAny: ['kitchen.view'], group: 'Main', hidden: true },
  { href: '/bar', label: 'Bar', title: 'Kitchen', subtitle: 'Bar station view inside the unified KDS', permissionsAny: ['kitchen.view'], group: 'Main', hidden: true },
  { href: '/expo', label: 'Expo / Pass', title: 'Kitchen', subtitle: 'Expo/pass view inside the unified KDS', permissionsAny: ['kitchen.view'], group: 'Main', hidden: true },
  { href: '/customer-display', navigationHref: '/customer-display?setup=1&channel=main', label: 'Customer Display Setup', title: 'Customer Display', subtitle: 'Pair an optional guest screen for live order totals', permissionsAny: ['approvals.manage'], group: 'Main' },
  { href: '/orders', label: 'Orders', title: 'Orders', subtitle: 'Search, review, and control POS orders across shifts', permissionsAny: ['orders.manage', 'pos.use'], group: 'Main' },
  { href: '/registers', label: 'Registers', title: 'Registers', subtitle: 'Outlets, register mapping, and drawer ownership', permissionsAny: ['registers.view'], group: 'Operations' },
  { href: '/sessions', label: 'Sessions', title: 'Sessions', subtitle: 'Open and close shifts with drawer reconciliation', permissionsAny: ['registers.view'], group: 'Operations' },
  { href: '/cash-movements', label: 'Cash Movements', title: 'Cash Movements', subtitle: 'Paid in, paid out, float, and drawer adjustments', permissionsAny: ['cash.manage'], group: 'Operations' },
  { href: '/room-charges', label: 'Room Charges', title: 'Room Charges', subtitle: 'Track pending folio charges, disputes, and guest billing', permissionsAny: ['room_charges.view', 'room_charges.manage', 'orders.manage'], group: 'Operations' },
  { href: '/catalog', label: 'Catalog', title: 'Catalog', subtitle: 'Imported sellable items, pricing, availability, and sync', permissionsAny: ['catalog.view'], group: 'Operations' },
  { href: '/recipes', label: 'Recipes', title: 'Recipe Library', subtitle: 'Open staff recipe PDFs linked to Accounting dishes', permissionsAny: ['recipes.view'], group: 'Operations' },
  { href: '/sync', label: 'Sync Queue', title: 'Sync Queue', subtitle: 'Outbox-based accounting sync and retry management', permissionsAny: ['sync.view'], group: 'Admin' },
  { href: '/settings', label: 'Settings', title: 'Settings', subtitle: 'Accounting connection, sync mode, and UI preferences', permissionsAny: ['settings.manage'], group: 'Admin' },
  { href: '/users', label: 'Users', title: 'Users', subtitle: 'Cashier, manager, and kitchen user access', permissionsAny: ['users.manage'], group: 'Admin' },
  { href: '/audit', label: 'Audit Log', title: 'Audit Log', subtitle: 'Review user actions, audits, linked entities, and approval decisions', permissionsAny: ['audit.view', 'reports.view', 'settings.manage'], group: 'Admin' },
];

export function normalizeRoutePath(pathname) {
  if (!pathname) return '/';
  const withoutQuery = pathname.split('?')[0].split('#')[0] || '/';
  if (withoutQuery === '/') return '/';
  return withoutQuery.replace(/\/+$/, '') || '/';
}

export function getRouteMeta(pathname) {
  const normalized = normalizeRoutePath(pathname);
  const exact = ROUTE_ITEMS.find((route) => route.href === normalized);
  if (exact) return exact;
  return ROUTE_ITEMS.find((route) => normalized.startsWith(`${route.href}/`)) || null;
}

export function isKnownRoute(pathname) {
  const normalized = normalizeRoutePath(pathname);
  return normalized === '/login' || normalized === '/customer-display' || !!getRouteMeta(normalized);
}

export function getRouteTitle(pathname) {
  return getRouteMeta(pathname)?.title || 'POS Cloud';
}

export function getRouteSubtitle(pathname) {
  return getRouteMeta(pathname)?.subtitle || 'Fast cashier operations with clean accounting sync';
}

export function routeGroups() {
  const groups = ROUTE_ITEMS.reduce((acc, item) => {
    acc[item.group] = acc[item.group] || [];
    acc[item.group].push(item);
    return acc;
  }, {});
  return Object.entries(groups).map(([label, items]) => ({ label, items }));
}

export function routeCanAccess(user, pathname) {
  const normalized = normalizeRoutePath(pathname);
  if (normalized === '/login' || normalized === '/customer-display') return true;
  const route = getRouteMeta(normalized);
  // Unknown routes are not authorization failures. Let Next render not-found.
  if (!route) return true;
  if (!route.permissionsAny || !route.permissionsAny.length) return true;
  return route.permissionsAny.some((permission) => canAccess(user, permission));
}

export function defaultRouteForUser(user) {
  if (canAccess(user, 'pos.use')) return '/pos';
  if (canAccess(user, 'kitchen.view')) return '/kitchen';
  if (canAccess(user, 'dashboard.view')) return '/dashboard';
  const first = ROUTE_ITEMS.find((item) => !item.hidden && item.permissionsAny?.some((permission) => canAccess(user, permission)));
  return first?.href || '/login';
}

export function visibleRouteGroups(user) {
  return routeGroups()
    .map((group) => ({ ...group, items: group.items.filter((item) => !item.hidden && item.permissionsAny.some((permission) => canAccess(user, permission))) }))
    .filter((group) => group.items.length > 0);
}
