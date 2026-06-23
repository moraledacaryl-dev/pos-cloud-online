'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { useCurrentUser } from '../lib/useCurrentUser';
import { visibleRouteGroups } from '../lib/routes';

const SIDEBAR_KEY = 'pos_sidebar_collapsed_v1';
const connectedApps = [
  { label: 'Staff & Payroll', href: process.env.NEXT_PUBLIC_STAFF_PAYROLL_APP_URL },
  { label: 'Operations', href: process.env.NEXT_PUBLIC_OPERATIONS_APP_URL },
  { label: 'Accounting', href: process.env.NEXT_PUBLIC_ACCOUNTING_APP_URL },
].filter((item) => item.href);

function collapsedLabel(label) {
  return label
    .split('&')[0]
    .trim()
    .split(' ')
    .map((part) => part.slice(0, 1).toUpperCase())
    .join('')
    .slice(0, 2);
}

export default function Sidebar() {
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
    document.documentElement.style.setProperty('--sidebar-width', collapsed ? '94px' : '286px');
    if (typeof window !== 'undefined') window.localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  const visibleGroups = useMemo(() => visibleRouteGroups(user), [user]);

  return (
    <aside className={collapsed ? 'sidebar collapsed' : 'sidebar'}>
      <div className="brand">
        <div className="brand-badge">PO</div>
        {!collapsed && (
          <div>
            <h2>Dedicated POS</h2>
            <div className="small muted-on-dark">Fast sales and drawer control</div>
          </div>
        )}
        <button type="button" className="sidebar-toggle" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={() => setCollapsed((v) => !v)}>
          {collapsed ? '>' : '<'}
        </button>
      </div>
      <nav>
        {visibleGroups.map((group) => (
          <div key={group.label} className="nav-group">
            {!collapsed && <div className="nav-group-label">{group.label}</div>}
            {group.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(item.href + '/');
              return (
                <Link key={item.href} href={item.href} className={active ? 'active' : ''} title={collapsed ? item.label : undefined}>
                  {collapsed ? collapsedLabel(item.label) : item.label}
                </Link>
              );
            })}
          </div>
        ))}
        {connectedApps.length > 0 && (
          <div className="nav-group">
            {!collapsed && <div className="nav-group-label">Connected Apps</div>}
            {connectedApps.map((item) => (
              <a key={item.label} href={item.href} rel="noreferrer" title={collapsed ? item.label : undefined}>
                {collapsed ? collapsedLabel(item.label) : item.label}
              </a>
            ))}
          </div>
        )}
      </nav>
    </aside>
  );
}
