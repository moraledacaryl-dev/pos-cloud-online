'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { forwardRef, useEffect, useMemo, useState } from 'react';
import { useCurrentUser } from '../lib/useCurrentUser';
import { visibleRouteGroups } from '../lib/routes';

const SIDEBAR_KEY = 'pos_sidebar_collapsed_v1';
const connectedApps = [
  { label: 'Staff & Payroll', href: process.env.NEXT_PUBLIC_STAFF_PAYROLL_APP_URL },
  { label: 'Operations', href: process.env.NEXT_PUBLIC_OPERATIONS_APP_URL },
  { label: 'Accounting', href: process.env.NEXT_PUBLIC_ACCOUNTING_APP_URL },
].filter((item) => item.href);

const NAV_ICON_PATHS = {
  '/dashboard': ['M4 4h6v6H4z', 'M14 4h6v6h-6z', 'M4 14h6v6H4z', 'M14 14h6v6h-6z'],
  '/pos': ['M4 5h16v12H4z', 'M8 21h8', 'M12 17v4', 'M8 9h8', 'M8 13h5'],
  '/kitchen': ['M4 15h16', 'M6 15a6 6 0 0 1 12 0', 'M12 6V4', 'M9 4h6'],
  '/customer-display': ['M3 5h18v12H3z', 'M8 21h8', 'M12 17v4'],
  '/orders': ['M7 4h10', 'M9 2h6v4H9z', 'M6 4h12v17H6z', 'M9 10h6', 'M9 14h6'],
  '/registers': ['M4 8h16v12H4z', 'M7 4h10v4H7z', 'M7 12h4', 'M15 12h2', 'M7 16h10'],
  '/sessions': ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M12 7v5l3 2'],
  '/cash-movements': ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M15 9.5c-.6-.9-1.6-1.5-3-1.5-1.7 0-3 1-3 2.3 0 3.4 6 1.4 6 4.4 0 1.3-1.3 2.3-3 2.3-1.4 0-2.5-.6-3-1.5', 'M12 6v12'],
  '/room-charges': ['M3 18v-7h18v7', 'M5 11V6h7v5', 'M12 8h7a2 2 0 0 1 2 2v1', 'M3 21v-3', 'M21 21v-3'],
  '/catalog': ['M4 4h7v7H4z', 'M13 4h7v7h-7z', 'M4 13h7v7H4z', 'M13 13h7v7h-7z'],
  '/recipes': ['M4 5a3 3 0 0 1 3-3h5v18H7a3 3 0 0 0-3 3z', 'M20 5a3 3 0 0 0-3-3h-5v18h5a3 3 0 0 1 3 3z'],
  '/sync': ['M20 7h-5V2', 'M20 7l-3.2-3.2A8 8 0 0 0 4.6 7', 'M4 17h5v5', 'M4 17l3.2 3.2A8 8 0 0 0 19.4 17'],
  '/settings': ['M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z', 'M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21h-4v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3v-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5V3h4v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.1v4h-.1a1.7 1.7 0 0 0-1.5 1z'],
  '/users': ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', 'M22 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75'],
  '/audit': ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', 'M9 12l2 2 4-4'],
};

function NavIcon({ href, external = false }) {
  const paths = external
    ? ['M14 3h7v7', 'M10 14 21 3', 'M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5']
    : NAV_ICON_PATHS[href] || ['M5 5h14v14H5z'];

  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      {paths.map((path) => <path key={path} d={path} />)}
    </svg>
  );
}

function collapsedLabel(label) {
  return label
    .split('&')[0]
    .trim()
    .split(' ')
    .map((part) => part.slice(0, 1).toUpperCase())
    .join('')
    .slice(0, 2);
}

const Sidebar = forwardRef(function Sidebar({ mobileOpen = false, onNavigate, onClose }, ref) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const { user } = useCurrentUser();

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = window.localStorage.getItem(SIDEBAR_KEY);
    setCollapsed(stored === '1');
  }, []);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    document.documentElement.style.setProperty('--sidebar-width', collapsed ? '76px' : '248px');
    if (typeof window !== 'undefined') window.localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  const visibleGroups = useMemo(() => visibleRouteGroups(user), [user]);
  const className = `${collapsed ? 'sidebar collapsed' : 'sidebar'}${mobileOpen ? ' mobile-open' : ''}`;

  return (
    <aside ref={ref} id="primary-navigation" className={className} aria-label="Primary navigation">
      <div className="brand">
        <div className="brand-badge" aria-hidden="true">PO</div>
        <div className="brand-copy">
          <h2>Dedicated POS</h2>
          <div className="small muted-on-dark">Fast sales and drawer control</div>
        </div>
        <button type="button" className="drawer-close" aria-label="Close navigation menu" onClick={onClose}>×</button>
        <button type="button" className="sidebar-toggle" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={() => setCollapsed((v) => !v)}>
          {collapsed ? '>' : '<'}
        </button>
      </div>
      <nav aria-label="POS sections">
        {visibleGroups.map((group) => (
          <div key={group.label} className="nav-group">
            <div className="nav-group-label">{group.label}</div>
            {group.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(item.href + '/');
              return (
                <Link
                  key={item.href}
                  href={item.navigationHref || item.href}
                  className={active ? 'active' : ''}
                  aria-current={active ? 'page' : undefined}
                  title={collapsed ? item.label : undefined}
                  onClick={onNavigate}
                >
                  <span className="nav-icon"><NavIcon href={item.href} /></span>
                  <span className="nav-abbr" aria-hidden="true">{collapsedLabel(item.label)}</span>
                  <span className="nav-label">{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
        {connectedApps.length > 0 && (
          <div className="nav-group">
            <div className="nav-group-label">Connected Apps</div>
            {connectedApps.map((item) => (
              <a key={item.label} href={item.href} rel="noreferrer" title={collapsed ? item.label : undefined} onClick={onNavigate}>
                <span className="nav-icon"><NavIcon external /></span>
                <span className="nav-abbr" aria-hidden="true">{collapsedLabel(item.label)}</span>
                <span className="nav-label">{item.label}</span>
              </a>
            ))}
          </div>
        )}
      </nav>
      <div className="sidebar-footer">
        <div className="sidebar-user-avatar" aria-hidden="true">
          {String(user?.full_name || user?.display_name || user?.username || 'U').slice(0, 1).toUpperCase()}
        </div>
        <div className="sidebar-user-copy">
          <strong>{user?.full_name || user?.display_name || user?.username || 'POS user'}</strong>
          <span>{String(user?.role || 'staff').replaceAll('_', ' ')}</span>
        </div>
      </div>
    </aside>
  );
});

export default Sidebar;
