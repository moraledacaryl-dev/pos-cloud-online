'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { fetchSyncStatus } from '../lib/api';
import { useCurrentUser } from '../lib/useCurrentUser';

function summarizeHealth(health, requestError) {
  if (requestError) return { tone: 'danger', label: 'POS server connection needs attention', detail: requestError };
  if (!health) return { tone: 'info', label: 'Checking POS sync health', detail: 'Loading current diagnostics...' };
  const issues = [];
  const migration = health.database?.migration;
  if (!health.database?.ok || migration?.requires_upgrade) issues.push('database migration required');
  if (!health.accounting_api?.ok) issues.push('Accounting API unreachable');
  if (health.sync_worker?.is_stale) issues.push('sync worker heartbeat stale');
  if (Number(health.outbox?.failed || 0) > 0) issues.push(`${health.outbox.failed} failed sync event(s)`);
  if (Number(health.outbox?.blocked || 0) > 0) issues.push(`${health.outbox.blocked} blocked sync event(s)`);
  if (issues.length) return { tone: issues.some((item) => item.includes('unreachable') || item.includes('migration')) ? 'danger' : 'warn', label: 'POS sync needs attention', detail: issues.join(' / ') };
  return { tone: 'success', label: 'POS sync healthy', detail: `${Number(health.outbox?.due_now || 0)} queued now / worker active` };
}

export default function SyncHealthBanner() {
  const { loaded, user, can } = useCurrentUser();
  const [health, setHealth] = useState(null);
  const [requestError, setRequestError] = useState('');

  useEffect(() => {
    if (!loaded || !user) return undefined;
    let active = true;
    async function load() {
      try {
        const data = await fetchSyncStatus();
        if (!active) return;
        setHealth(data || null);
        setRequestError('');
      } catch (e) {
        if (!active) return;
        setRequestError(e.message || 'Could not read sync health.');
      }
    }
    load().catch(console.error);
    const timer = window.setInterval(() => load().catch(console.error), 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [loaded, user]);

  const summary = useMemo(() => summarizeHealth(health, requestError), [health, requestError]);
  if (!loaded || !user) return null;

  return (
    <div className={`sync-health-banner ${summary.tone}`}>
      <div><strong>{summary.label}</strong><span>{summary.detail}</span></div>
      {can('sync.view') ? <Link href="/sync">Open diagnostics</Link> : <span>Tell a manager if this is not green.</span>}
    </div>
  );
}
