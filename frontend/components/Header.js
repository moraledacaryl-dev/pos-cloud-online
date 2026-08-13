'use client';

import { usePathname } from 'next/navigation';
import { logoutSession } from '../lib/api';
import { getRouteTitle, getRouteSubtitle } from '../lib/routes';

export default function Header() {
  const pathname = usePathname();
  const title = getRouteTitle(pathname);
  const subtitle = getRouteSubtitle(pathname);

  async function handleLogout() {
    try { await logoutSession(); } catch {}
    if (typeof window !== 'undefined') window.location.href = '/login';
  }

  return (
    <header className="topbar">
      <div>
        <div className="topbar-title">{title}</div>
        <div className="topbar-subtitle">{subtitle}</div>
      </div>
      {pathname !== '/login' && <button className="secondary" onClick={handleLogout}>Logout</button>}
    </header>
  );
}
