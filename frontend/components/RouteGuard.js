'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { logoutSession } from '../lib/api';
import { useCurrentUser } from '../lib/useCurrentUser';
import { defaultRouteForUser, getRouteMeta, normalizeRoutePath, routeCanAccess } from '../lib/routes';

export default function RouteGuard({ children }) {
  const pathname = usePathname();
  const normalized = normalizeRoutePath(pathname);
  const { loaded, user } = useCurrentUser();
  const [loggingOut, setLoggingOut] = useState(false);
  const isLogin = normalized === '/login';
  const isCustomerDisplay = normalized === '/customer-display';
  const isPublic = isLogin || isCustomerDisplay;
  const route = getRouteMeta(normalized);
  const isKnownProtectedRoute = !!route && !isPublic;

  useEffect(() => {
    if (isPublic || !loaded || user) return;
    const next = normalized && normalized !== '/' ? `?next=${encodeURIComponent(normalized)}` : '';
    window.location.replace(`/login${next}`);
  }, [isPublic, loaded, normalized, user]);

  useEffect(() => {
    if (!isLogin || !loaded || !user) return;
    const target = defaultRouteForUser(user);
    if (target && target !== '/login') window.location.replace(target);
  }, [isLogin, loaded, user]);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logoutSession();
    } catch {
      // Clearing the server session is best-effort here; login remains the safe destination.
    } finally {
      window.location.replace('/login');
    }
  }

  if (!loaded && !isPublic) {
    return (
      <section className="section">
        <h1>Loading Access</h1>
        <p className="muted">Checking your permissions...</p>
      </section>
    );
  }

  if (!isPublic && loaded && !user) {
    return (
      <section className="section">
        <h1>Authentication Required</h1>
        <p className="muted">Your POS session is not active. Opening login...</p>
      </section>
    );
  }

  if (isLogin && loaded && user) {
    return (
      <section className="section">
        <h1>Opening Workspace</h1>
        <p className="muted">Your session is already active.</p>
      </section>
    );
  }

  // Unknown routes are deliberately passed through so Next.js can render its
  // canonical not-found UI instead of misclassifying them as authorization failures.
  if (!route && !isPublic) return children;

  if (!isKnownProtectedRoute || routeCanAccess(user, normalized)) return children;

  const fallback = defaultRouteForUser(user) || '/';

  return (
    <section className="section" role="alert" data-route-status="403">
      <h1>Access Restricted</h1>
      <p className="muted">This page exists, but your account does not have permission to open it.</p>
      <div className="route-denied-actions">
        <Link className="button-link" href={fallback}>Open my workspace</Link>
        <button type="button" className="secondary" disabled={loggingOut} onClick={handleLogout}>
          {loggingOut ? 'Signing out…' : 'Sign out'}
        </button>
      </div>
    </section>
  );
}
