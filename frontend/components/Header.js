'use client';

import { usePathname } from 'next/navigation';
import { logoutSession } from '../lib/api';
import { clearLastReceipt } from '../lib/receipt';
import { getRouteTitle, getRouteSubtitle } from '../lib/routes';

export default function Header({ menuButtonRef, menuOpen = false, onMenuToggle }) {
  const pathname = usePathname();
  const title = getRouteTitle(pathname);
  const subtitle = getRouteSubtitle(pathname);

  async function handleLogout() {
    try { await logoutSession(); } catch {}
    clearLastReceipt();
    if (typeof window !== 'undefined') window.location.href = '/login';
  }

  return (
    <header className="topbar">
      <div className="topbar-leading">
        <button
          ref={menuButtonRef}
          type="button"
          className="mobile-menu-button secondary"
          aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={menuOpen}
          aria-controls="primary-navigation"
          onClick={onMenuToggle}
        >
          <span aria-hidden="true">☰</span>
        </button>
        <div>
          <div className="topbar-title">{title}</div>
          <div className="topbar-subtitle">{subtitle}</div>
        </div>
      </div>
      {pathname !== '/login' && <button className="secondary" onClick={handleLogout}>Logout</button>}
    </header>
  );
}
