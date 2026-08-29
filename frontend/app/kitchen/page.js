'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchKitchenTickets, updateKitchenLineStatus } from '../../lib/api';
import { createKitchenStreamTicket, kitchenStreamUrl } from '../../lib/kdsStream';
import { badgeClass, kitchenStatusLabel, sourceLabel, statusBadgeClass, useGroupedKitchenTickets } from '../../lib/kitchen';
import ActionModal from '../../components/ActionModal';

const STATIONS = [
  { key: '', label: 'All' },
  { key: 'kitchen', label: 'Kitchen' },
  { key: 'cafe', label: 'Cafe' },
  { key: 'bar', label: 'Bar' },
  { key: 'expo', label: 'Expo' },
];

const VIEWS = [
  { key: 'active', label: 'Active', statuses: ['queued', 'acknowledged', 'in_progress'] },
  { key: 'held', label: 'Held', statuses: ['held'] },
  { key: 'ready', label: 'Ready', statuses: ['ready'] },
  { key: 'all_day', label: 'All Day', statuses: ['held', 'queued', 'acknowledged', 'in_progress', 'ready'] },
  { key: 'lines', label: 'Line View', statuses: ['held', 'queued', 'acknowledged', 'in_progress', 'ready'] },
];

function stationDefaults(initialStation) {
  if (initialStation === 'expo') return { station: 'expo', view: 'ready', title: 'Kitchen' };
  if (initialStation === 'bar') return { station: 'bar', view: 'active', title: 'Kitchen' };
  return { station: initialStation || '', view: 'active', title: 'Kitchen' };
}

function formatDuration(minutes) {
  if (minutes == null) return '-';
  const m = Number(minutes || 0);
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return `${m}m`;
}

function ticketAgeClass(minutes) {
  const age = Number(minutes || 0);
  if (age >= 25) return 'danger';
  if (age >= 15) return 'warn';
  return 'info';
}

function allDayRows(tickets) {
  const map = new Map();
  tickets.forEach((line) => {
    const key = `${line.prep_station || 'kitchen'}-${line.item_name_snapshot}`;
    const row = map.get(key) || { key, station: line.prep_station || 'kitchen', item: line.item_name_snapshot, held: 0, new: 0, started: 0, ready: 0, total: 0 };
    const qty = Number(line.quantity || 0);
    row.total += qty;
    if (line.kitchen_status === 'held') row.held += qty;
    else if (line.kitchen_status === 'ready') row.ready += qty;
    else if (line.kitchen_status === 'in_progress') row.started += qty;
    else row.new += qty;
    map.set(key, row);
  });
  return Array.from(map.values()).sort((a, b) => a.station.localeCompare(b.station) || a.item.localeCompare(b.item));
}

export default function KitchenPage({ initialStation = '', initialView = '' }) {
  const defaults = stationDefaults(initialStation);
  const [station, setStation] = useState(defaults.station);
  const [view, setView] = useState(initialView || defaults.view);
  const [tickets, setTickets] = useState([]);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [connectionState, setConnectionState] = useState('connecting');
  const [newTicketCount, setNewTicketCount] = useState(0);
  const [partialLine, setPartialLine] = useState(null);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const seenRef = useRef(new Set());
  const audioRef = useRef(null);
  const streamRef = useRef(null);

  const currentView = VIEWS.find((item) => item.key === view) || VIEWS[0];
  const statuses = currentView.statuses;

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const requestedStation = params.get('station');
    const requestedView = params.get('view');
    if (STATIONS.some((item) => item.key === requestedStation)) setStation(requestedStation || '');
    if (VIEWS.some((item) => item.key === requestedView)) setView(requestedView);
  }, []);

  async function playAlert() {
    if (!soundEnabled || !audioRef.current) return;
    try {
      audioRef.current.currentTime = 0;
      await audioRef.current.play();
    } catch {
      setSoundEnabled(false);
      setNotice('Kitchen sound was blocked by the browser. Select Enable sound to turn alerts back on.');
    }
  }

  async function enableSound() {
    if (!audioRef.current) return;
    setNotice('');
    try {
      audioRef.current.currentTime = 0;
      await audioRef.current.play();
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setSoundEnabled(true);
      setNotice('Kitchen sound alerts enabled.');
    } catch {
      setSoundEnabled(false);
      setNotice('Kitchen sound could not be enabled in this browser.');
    }
  }

  async function loadTickets() {
    try {
      const rows = await fetchKitchenTickets({ station: station || undefined, statuses });
      const safeRows = Array.isArray(rows) ? rows : [];
      const incoming = safeRows.filter((row) => !seenRef.current.has(row.line_id));
      safeRows.forEach((row) => seenRef.current.add(row.line_id));
      if (incoming.length && view === 'active') {
        setNewTicketCount((prev) => prev + incoming.length);
        await playAlert();
      }
      setTickets(safeRows);
      setError('');
    } catch (e) {
      setError(e.message || 'Failed to load kitchen tickets.');
    }
  }

  useEffect(() => { loadTickets().catch(console.error); }, [station, view, soundEnabled]);

  useEffect(() => {
    let cancelled = false;
    let es = null;
    let reconnectTimer = null;

    const connect = async () => {
      setConnectionState('connecting');
      try {
        const grant = await createKitchenStreamTicket(station);
        if (cancelled) return;
        es = new EventSource(kitchenStreamUrl(station, grant.ticket));
        streamRef.current = es;
        es.addEventListener('hello', () => setConnectionState('connected'));
        const refresh = () => {
          setConnectionState('connected');
          loadTickets().catch(() => {});
        };
        ['ticket_created', 'ticket_updated', 'ticket_status_updated', 'ticket_finalized', 'ticket_line_updated'].forEach((eventName) => es.addEventListener(eventName, refresh));
        es.addEventListener('stream_expiring', () => {
          es?.close();
          if (!cancelled) reconnectTimer = window.setTimeout(() => connect().catch(() => {}), 250);
        });
        es.onerror = () => {
          setConnectionState('disconnected');
          es?.close();
          if (!cancelled) reconnectTimer = window.setTimeout(() => connect().catch(() => {}), 1500);
        };
      } catch (e) {
        setConnectionState('disconnected');
        if (!cancelled) reconnectTimer = window.setTimeout(() => connect().catch(() => {}), 2000);
      }
    };

    connect().catch(() => {});
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      es?.close();
      streamRef.current = null;
    };
  }, [station, view]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key.toLowerCase() === 'r') loadTickets().catch(() => {});
      if (e.key === '1') setView('active');
      if (e.key === '2') setView('held');
      if (e.key === '3') setView('ready');
      if (e.key === '4') setView('all_day');
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'p') {
        e.preventDefault();
        window.print();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [station, view, soundEnabled]);

  const grouped = useGroupedKitchenTickets(tickets);
  const allDay = useMemo(() => allDayRows(tickets), [tickets]);

  async function pushStatus(lineId, payload, successMessage) {
    setError('');
    setNotice('');
    try {
      await updateKitchenLineStatus(lineId, payload);
      setNotice(successMessage);
      await loadTickets();
    } catch (e) {
      setError(e.message || 'Failed to update line status.');
    }
  }

  async function handlePartialReady(row, value) {
    const quantity = Number(row.quantity || 0);
    const readyQuantity = Number(value || 0);
    if (!readyQuantity || readyQuantity <= 0 || readyQuantity >= quantity) {
      throw new Error(`Enter a quantity between 1 and ${Math.max(quantity - 1, 1)}.`);
    }
    await pushStatus(row.line_id, { kitchen_status: 'in_progress', item_readiness: 'partial', ready_quantity: readyQuantity }, `${row.item_name_snapshot} partially ready.`);
  }

  function lineButtons(row) {
    const buttons = [];
    if (row.kitchen_status === 'held') {
      buttons.push(<button key="fire" type="button" className="primary" onClick={() => pushStatus(row.line_id, { kitchen_status: 'queued' }, `${row.item_name_snapshot} fired.`)}>Fire</button>);
      return buttons;
    }
    if (['queued', 'acknowledged'].includes(row.kitchen_status)) {
      buttons.push(<button key="start" type="button" className="primary" onClick={() => pushStatus(row.line_id, { kitchen_status: 'in_progress' }, `${row.item_name_snapshot} started.`)}>Start</button>);
      buttons.push(<button key="hold" type="button" className="secondary" onClick={() => pushStatus(row.line_id, { kitchen_status: 'held' }, `${row.item_name_snapshot} held.`)}>Hold</button>);
    }
    if (row.kitchen_status === 'in_progress' && Number(row.quantity || 0) > 1) {
      buttons.push(<button key="partial" type="button" className="secondary" onClick={() => setPartialLine(row)}>Partial</button>);
    }
    if (['queued', 'acknowledged', 'in_progress'].includes(row.kitchen_status)) {
      buttons.push(<button key="ready" type="button" className="secondary" onClick={() => pushStatus(row.line_id, { kitchen_status: 'ready' }, `${row.item_name_snapshot} ready.`)}>Ready</button>);
    }
    if (row.kitchen_status === 'ready') {
      buttons.push(<button key="serve" type="button" className="primary" onClick={() => pushStatus(row.line_id, { kitchen_status: 'served' }, `${row.item_name_snapshot} served.`)}>Served</button>);
      buttons.push(<button key="recall" type="button" className="secondary" onClick={() => pushStatus(row.line_id, { kitchen_status: 'in_progress' }, `${row.item_name_snapshot} recalled.`)}>Recall</button>);
    }
    return buttons;
  }

  function renderLine(line) {
    return (
      <div key={line.line_id} className={`kds-line status-${line.kitchen_status || 'queued'}`}>
        <div className="kds-line-main">
          <strong>{Number(line.quantity || 1)}x</strong>
          <span>{line.item_name_snapshot}</span>
        </div>
        {line.note && <div className="kds-line-note">{line.note}</div>}
        <div className="kds-line-meta">
          <span className={`badge ${statusBadgeClass(line.kitchen_status)}`}>{kitchenStatusLabel(line.kitchen_status)}</span>
          <span className="small muted">{line.prep_station || 'kitchen'}</span>
          {line.ready_quantity ? <span className="small muted">{line.ready_quantity}/{line.quantity} ready</span> : null}
        </div>
        <div className="kds-actions">{lineButtons(line)}</div>
      </div>
    );
  }

  return (
    <div className="kds-page">
      <audio ref={audioRef} src="/sounds/kds-alert.wav" preload="auto" />

      <section className="section kds-topbar">
        <div>
          <h1>{defaults.title}</h1>
          <p className="muted">One kitchen screen for active work, held items, ready orders, and all-day totals.</p>
        </div>
        <div className="kds-top-actions">
          <span className={`badge ${connectionState === 'connected' ? 'success' : connectionState === 'connecting' ? 'warn' : 'danger'}`}>{connectionState}</span>
          <span className={`badge ${newTicketCount ? 'warn' : 'info'}`}>{newTicketCount ? `${newTicketCount} new` : 'No new'}</span>
          <button type="button" className="secondary" aria-pressed={soundEnabled} onClick={() => enableSound().catch(() => {})}>{soundEnabled ? 'Sound enabled' : 'Enable sound'}</button>
          <button type="button" className="secondary" onClick={() => { setNewTicketCount(0); loadTickets().catch(() => {}); }}>Refresh</button>
          <button type="button" className="secondary" onClick={() => window.print()}>Print</button>
        </div>
      </section>

      <section className="section kds-controls">
        <div className="segmented kds-segmented">
          {STATIONS.map((item) => <button key={item.key || 'all'} type="button" className={`toggle-btn ${station === item.key ? 'on' : ''}`} onClick={() => setStation(item.key)}>{item.label}</button>)}
        </div>
        <div className="segmented kds-segmented">
          {VIEWS.map((item) => <button key={item.key} type="button" className={`toggle-btn ${view === item.key ? 'on' : ''}`} onClick={() => setView(item.key)}>{item.label}</button>)}
        </div>
      </section>

      {!!notice && <p className="notice-text">{notice}</p>}
      {!!error && <p className="error-text">{error}</p>}

      {view === 'all_day' ? (
        <section className="section kds-all-day">
          <div className="kds-section-head">
            <h2>All Day</h2>
            <span className="muted">{allDay.length} item groups</span>
          </div>
          <div className="kds-all-day-grid">
            {allDay.map((row) => (
              <article key={row.key} className="kds-all-day-row">
                <div><strong>{row.item}</strong><span>{row.station}</span></div>
                <div className="kds-all-day-counts">
                  <span>{row.total} total</span>
                  {!!row.held && <span>{row.held} held</span>}
                  {!!row.new && <span>{row.new} new</span>}
                  {!!row.started && <span>{row.started} started</span>}
                  {!!row.ready && <span>{row.ready} ready</span>}
                </div>
              </article>
            ))}
          </div>
          {!allDay.length && <p className="muted">No open kitchen items.</p>}
        </section>
      ) : view === 'lines' ? (
        <section className="section">
          <div className="kds-line-list">{tickets.map(renderLine)}</div>
          {!tickets.length && <p className="muted">No matching lines.</p>}
        </section>
      ) : (
        <section className="kds-ticket-grid">
          {grouped.map((ticket) => (
            <article key={ticket.key} className={`kds-ticket priority-${ticket.priority || 'normal'}`}>
              <header className="kds-ticket-header">
                <div>
                  <h2>{ticket.order_no || `#${ticket.order_id}`}</h2>
                  <p>{sourceLabel(ticket)} · {ticket.table_label || 'No table'} · {ticket.guest_name || 'Walk-in'}</p>
                </div>
                <div className="kds-ticket-badges">
                  <span className={`badge ${badgeClass(ticket.priority)}`}>{ticket.priority || 'normal'}</span>
                  <span className={`badge ${ticketAgeClass(ticket.age_minutes)}`}>{formatDuration(ticket.age_minutes)}</span>
                </div>
              </header>
              <div className="kds-ticket-lines">{ticket.lines.map(renderLine)}</div>
            </article>
          ))}
          {!grouped.length && <section className="section"><p className="muted">No tickets in this view.</p></section>}
        </section>
      )}
      <ActionModal
        open={!!partialLine}
        title={`Mark ${partialLine?.item_name_snapshot || 'item'} partially ready`}
        description={`Enter the ready quantity. The full line contains ${partialLine?.quantity || 0}.`}
        fieldLabel="Ready quantity"
        inputType="number"
        min="1"
        max={Math.max(Number(partialLine?.quantity || 1) - 1, 1)}
        defaultValue={Math.max(Number(partialLine?.quantity || 1) - 1, 1)}
        required
        confirmLabel="Save partial readiness"
        tone="normal"
        onClose={() => setPartialLine(null)}
        onConfirm={(value) => handlePartialReady(partialLine, value)}
      />
    </div>
  );
}
