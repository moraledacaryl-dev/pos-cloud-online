'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { clearRefreshToken, clearToken } from '../lib/api';
import { useCurrentUser } from '../lib/useCurrentUser';
import { defaultRouteForUser, routeCanAccess } from '../lib/routes';

export default function RouteGuard({ children }) {
  const pathname = usePathname();
  const { loaded, user } = useCurrentUser();
  const isPublic = pathname === '/login' || pathname === '/customer-display';

  useEffect(() => {
    if (isPublic || !loaded || user) return;
    clearToken();
    clearRefreshToken();
    const next = pathname && pathname !== '/' ? `?next=${encodeURIComponent(pathname)}` : '';
    window.location.replace(`/login${next}`);
  }, [isPublic, loaded, pathname, user]);

  useEffect(() => {
    if (isPublic || !loaded || !user || routeCanAccess(user, pathname)) return;
    const target = defaultRouteForUser(user);
    if (target && target !== pathname) window.location.replace(target);
  }, [isPublic, loaded, pathname, user]);

  if (!loaded && pathname !== '/login' && pathname !== '/customer-display') {
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
        <h1>Opening Login</h1>
        <p className="muted">Your POS session is not active.</p>
      </section>
    );
  }

  if (pathname === '/login' || routeCanAccess(user, pathname)) {
    return children;
  }

  return (
    <section className="section">
      <h1>Access Restricted</h1>
      <p className="muted">Your account does not have permission for this page. Opening your allowed workspace...</p>
    </section>
  );
}
