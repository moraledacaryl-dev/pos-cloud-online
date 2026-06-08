export const ROLE_PERMISSION_FALLBACKS = {
  owner: ['*'],
  admin: ['*'],
  manager: [
    'dashboard.view', 'pos.use', 'orders.manage', 'orders.void', 'catalog.view', 'catalog.manage',
    'recipes.view', 'recipes.manage',
    'registers.view', 'registers.manage', 'sessions.manage', 'cash.manage', 'kitchen.view',
    'room_charges.view', 'room_charges.manage', 'sync.view', 'sync.manage', 'settings.manage',
    'reports.view', 'audit.view', 'approvals.view', 'approvals.manage', 'users.manage', 'roles.manage',
  ],
  cashier: [
    'dashboard.view', 'pos.use', 'orders.manage', 'catalog.view', 'registers.view', 
    'sessions.manage', 'cash.manage', 'room_charges.view', 'room_charges.manage', 'recipes.view',
  ],
  kitchen: ['dashboard.view', 'kitchen.view', 'catalog.view', 'recipes.view'],
};

export function effectivePermissions(user) {
  const explicit = Array.isArray(user?.permissions) ? user.permissions.filter(Boolean) : [];
  if (explicit.length) return new Set(explicit);
  const role = String(user?.role || '').toLowerCase();
  return new Set(ROLE_PERMISSION_FALLBACKS[role] || []);
}

export function canAccess(user, key) {
  if (!key) return true;
  const perms = effectivePermissions(user);
  if (perms.has('*')) return true;
  return perms.has(key);
}
