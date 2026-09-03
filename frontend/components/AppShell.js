'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useCurrentUser } from '../lib/useCurrentUser';
import Header from './Header';
import RouteGuard from './RouteGuard';
import Sidebar from './Sidebar';
import SyncHealthBanner from './SyncHealthBanner';

const STANDALONE_ROUTES = new Set(['/login', '/customer-display']);
const TERMINAL_ROUTES = new Set(['/pos']);
const MOBILE_BREAKPOINT = 1000;

export default function AppShell({ children }) {
  const pathname = usePathname();
  const isStandalone = STANDALONE_ROUTES.has(pathname);
  const isTerminal = TERMINAL_ROUTES.has(pathname);
  const showAppChrome = !isStandalone && !isTerminal;
  const { loaded, user } = useCurrentUser();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerRef = useRef(null);
  const openerRef = useRef(null);
  const mainShellRef = useRef(null);

  useEffect(() => {
    if (isStandalone || !loaded || user) return;
    const next = pathname && pathname !== '/' ? `?next=${encodeURIComponent(pathname)}` : '';
    window.location.replace(`/login${next}`);
  }, [isStandalone, loaded, pathname, user]);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!drawerOpen || typeof document === 'undefined') return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    mainShellRef.current?.setAttribute('inert', '');

    const drawer = drawerRef.current;
    const focusable = drawer?.querySelectorAll(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    const first = focusable?.[0];
    const last = focusable?.[focusable.length - 1];
    first?.focus();

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        setDrawerOpen(false);
        return;
      }
      if (event.key !== 'Tab' || !first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      mainShellRef.current?.removeAttribute('inert');
      document.removeEventListener('keydown', onKeyDown);
      openerRef.current?.focus();
    };
  }, [drawerOpen]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    function closeAtDesktop() {
      if (window.innerWidth > MOBILE_BREAKPOINT) setDrawerOpen(false);
    }
    window.addEventListener('resize', closeAtDesktop);
    return () => window.removeEventListener('resize', closeAtDesktop);
  }, []);

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

  const ContentElement = isStandalone ? 'div' : 'main';

  return (
    <div className={isStandalone ? 'app-shell standalone-shell' : isTerminal ? 'app-shell terminal-shell' : 'app-shell'}>
      {showAppChrome && (
        <>
          <Sidebar ref={drawerRef} mobileOpen={drawerOpen} onNavigate={() => setDrawerOpen(false)} onClose={() => setDrawerOpen(false)} />
          <button
            type="button"
            className={drawerOpen ? 'drawer-scrim open' : 'drawer-scrim'}
            aria-label="Close navigation menu"
            tabIndex={drawerOpen ? 0 : -1}
            onClick={() => setDrawerOpen(false)}
          />
        </>
      )}
      <div className="main-shell" ref={mainShellRef}>
        {showAppChrome && (
          <Header
            menuButtonRef={openerRef}
            menuOpen={drawerOpen}
            onMenuToggle={() => setDrawerOpen((open) => !open)}
          />
        )}
        {showAppChrome && <SyncHealthBanner />}
        <ContentElement className={isStandalone ? 'main standalone-main' : isTerminal ? 'main terminal-main' : 'main'}>
          <RouteGuard>{children}</RouteGuard>
        </ContentElement>
      </div>
    </div>
  );
}
