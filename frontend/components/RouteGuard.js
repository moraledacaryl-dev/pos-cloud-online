'use client';

import { usePathname } from 'next/navigation';
import { useCurrentUser } from '../lib/useCurrentUser';
import { routeCanAccess } from '../lib/routes';

export default function RouteGuard({ children }) {
  const pathname = usePathname();
  const { loaded, can, user } = useCurrentUser();

  if (!loaded && pathname !== '/login') {
    return (
      <section className="section">
        <h1>Loading Access</h1>
        <p className="muted">Checking your permissions...</p>
      </section>
    );
  }

  if (pathname === '/login' || routeCanAccess(user, pathname)) {
    return children;
  }

  return (
    <section className="section">
      <h1>Access Restricted</h1>
      <p className="muted">Your account does not have permission for this page.</p>
    </section>
  );
}
