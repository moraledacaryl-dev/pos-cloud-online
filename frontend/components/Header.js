'use client';

import { usePathname } from 'next/navigation';
import { clearRefreshToken, clearToken, getRefreshToken, logoutSession } from '../lib/api';
import { getRouteTitle, getRouteSubtitle } from '../lib/routes';

export default function Header() {
  const pathname = usePathname();
  const title = getRouteTitle(pathname);
  const subtitle = getRouteSubtitle(pathname);

  async function handleLogout() {
    try {
      const refresh = getRefreshToken();
      if (refresh) await logoutSession({ refresh_token: refresh });
    } catch {}
    clearToken();
    clearRefreshToken();
    if (typeof window !== 'undefined') window.location.href = '/login';
  }

  return (
    <header className="topbar">
      <div>
        <div className="topbar-title">{title}</div>
        <div className="topbar-subtitle">{subtitle}</div>
      </div>
      {pathname !== '/login' && (
        <button className="secondary" onClick={handleLogout}>
          Logout
        </button>
      )}
    </header>
  );
}
