'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useCurrentUser } from '../lib/useCurrentUser';
import Header from './Header';
import RouteGuard from './RouteGuard';
import Sidebar from './Sidebar';
import SyncHealthBanner from './SyncHealthBanner';

const STANDALONE_ROUTES = new Set(['/login', '/customer-display']);
const TERMINAL_ROUTES = new Set(['/pos']);

export default function AppShell({ children }) {
  const pathname = usePathname();
  const isStandalone = STANDALONE_ROUTES.has(pathname);
  const isTerminal = TERMINAL_ROUTES.has(pathname);
  const showAppChrome = !isStandalone && !isTerminal;
  const { loaded, user } = useCurrentUser();

  useEffect(() => {
    if (isStandalone || !loaded || user) return;
    const next = pathname && pathname !== '/' ? `?next=${encodeURIComponent(pathname)}` : '';
    window.location.replace(`/login${next}`);
  }, [isStandalone, loaded, pathname, user]);

  if (!isStandalone && !loaded) {
    return (
      <div className="app-shell standalone-shell">
        <main className="main standalone-main">
          <section className="section auth-status-card">
            <h1>Checking Access</h1>
            <p className="muted">Confirming the POS session before opening the terminal.</p>
          </section>
        </main>
      </div>
    );
  }

  if (!isStandalone && loaded && !user) {
    return (
      <div className="app-shell standalone-shell">
        <main className="main standalone-main">
          <section className="section auth-status-card">
            <h1>Opening Login</h1>
            <p className="muted">Your POS session is not active. Redirecting to login.</p>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className={isStandalone ? 'app-shell standalone-shell' : isTerminal ? 'app-shell terminal-shell' : 'app-shell'}>
      {showAppChrome && <Sidebar />}
      <div className="main-shell">
        {showAppChrome && <Header />}
        {showAppChrome && <SyncHealthBanner />}
        <main className={isStandalone ? 'main standalone-main' : isTerminal ? 'main terminal-main' : 'main'}>
          <RouteGuard>{children}</RouteGuard>
        </main>
      </div>
    </div>
  );
}
