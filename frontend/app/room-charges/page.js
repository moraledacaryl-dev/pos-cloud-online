"use client";

import { useEffect, useMemo, useState } from 'react';
import {
  createInHouseBooking,
  fetchInHouseBookings,
  fetchRoomCharges,
  updateInHouseBooking,
  updateRoomChargeStatus,
} from '../../lib/api';
import {
  filterRoomChargeQueue,
  roomChargeStatusMeta,
  summarizeRoomChargeQueue,
} from '../../lib/ui_contracts.mjs';

function todayISO() { return new Date().toISOString().slice(0, 10); }
function money(value) { return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

const STATUS_OPTIONS = ['', 'pending_frontdesk_post', 'posted_to_beds24', 'rejected', 'disputed', 'settled_at_frontdesk', 'written_off', 'cancelled'];
const STATUS_VIEWS = [
  { key: 'all', label: 'All' },
  { key: 'pending_frontdesk_post', label: 'Pending' },
  { key: 'posted_to_beds24', label: 'Posted' },
  { key: 'settled_at_frontdesk', label: 'Settled' },
  { key: 'attention', label: 'Needs review' },
];

const emptyBooking = { stay_date: todayISO(), room_number: '', guest_name: '', guest_label: '', arrival_date: '', departure_date: '', booking_status: 'in_house', beds24_booking_id: '', source: 'manual_snapshot', notes: '' };
const emptyStatus = { posting_status: 'posted_to_beds24', beds24_posting_reference: '', note: '', dispute_note: '', later_payment_status: '', payment_date: todayISO(), rejected_reason: '', bill_to: '' };

function statusTone(status) {
  return roomChargeStatusMeta(status).tone;
}

function syncStatusFormFromRow(row) {
  return {
    posting_status: row?.posting_status || 'posted_to_beds24',
    beds24_posting_reference: row?.beds24_posting_reference || '',
    note: row?.note || '',
    dispute_note: row?.dispute_note || '',
    later_payment_status: row?.later_payment_status || '',
    payment_date: row?.payment_date || todayISO(),
    rejected_reason: row?.rejected_reason || '',
    bill_to: row?.bill_to || '',
  };
}

export default function RoomChargesPage() {
  const [queue, setQueue] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState({ view: 'pending_frontdesk_post', stay_date: todayISO(), q: '' });
  const [bookingSearch, setBookingSearch] = useState('');
  const [bookingForm, setBookingForm] = useState(emptyBooking);
  const [statusForm, setStatusForm] = useState(emptyStatus);
  const [editingBookingId, setEditingBookingId] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  async function loadData({ silent = false } = {}) {
    if (!silent) setLoading(true);
    setError('');
    try {
      const [queueRows, bookingRows] = await Promise.all([
        fetchRoomCharges({ stay_date: filters.stay_date || todayISO(), limit: 300 }),
        fetchInHouseBookings({ stay_date: filters.stay_date || todayISO(), active_only: true, limit: 300 }),
      ]);
      setQueue(Array.isArray(queueRows) ? queueRows : []);
      setBookings(Array.isArray(bookingRows) ? bookingRows : []);
    } catch (e) {
      setError(e.message || 'Failed to load room charges.');
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => { loadData().catch(console.error); }, [filters.stay_date]);

  const summary = useMemo(() => summarizeRoomChargeQueue(queue), [queue]);
  const queueRows = useMemo(() => {
    if (filters.view === 'attention') {
      return filterRoomChargeQueue(queue.filter((row) => ['rejected', 'disputed', 'written_off'].includes(String(row.posting_status || '').toLowerCase())), { q: filters.q, stay_date: filters.stay_date });
    }
    return filterRoomChargeQueue(queue, {
      posting_status: filters.view === 'all' ? '' : filters.view,
      stay_date: filters.stay_date,
      q: filters.q,
    });
  }, [queue, filters]);

  const filteredBookings = useMemo(() => {
    const q = String(bookingSearch || '').trim().toLowerCase();
    if (!q) return bookings;
    return bookings.filter((row) => [row.room_number, row.guest_name, row.guest_label, row.beds24_booking_id].some((value) => String(value || '').toLowerCase().includes(q)));
  }, [bookings, bookingSearch]);

  useEffect(() => {
    if (!queueRows.length) {
      setSelected(null);
      return;
    }
    const found = selected ? queueRows.find((row) => row.id === selected.id) : null;
    const nextSelected = found || queueRows[0];
    setSelected(nextSelected);
    setStatusForm(syncStatusFormFromRow(nextSelected));
  }, [queueRows]);

  function selectQueueRow(row) {
    setSelected(row);
    setStatusForm(syncStatusFormFromRow(row));
  }

  async function handleStatusSubmit(event) {
    event.preventDefault();
    if (!selected?.id) return;
    setError('');
    setNotice('');
    try {
      const updated = await updateRoomChargeStatus(selected.id, statusForm);
      setSelected(updated);
      setStatusForm(syncStatusFormFromRow(updated));
      setNotice(`Room charge ${updated.posting_uuid} updated to ${updated.posting_status_label}.`);
      await loadData({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to update room charge status.');
    }
  }

  async function handleBookingSubmit(event) {
    event.preventDefault();
    setError('');
    setNotice('');
    try {
      const payload = {
        ...bookingForm,
        guest_name: bookingForm.guest_name || null,
        guest_label: bookingForm.guest_label || null,
        arrival_date: bookingForm.arrival_date || null,
        departure_date: bookingForm.departure_date || null,
        beds24_booking_id: bookingForm.beds24_booking_id || null,
        notes: bookingForm.notes || null,
      };
      if (editingBookingId) await updateInHouseBooking(editingBookingId, payload);
      else await createInHouseBooking(payload);
      setNotice(editingBookingId ? 'In-house booking updated.' : 'In-house booking added.');
      setBookingForm(emptyBooking);
      setEditingBookingId(null);
      await loadData({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to save in-house booking.');
    }
  }

  function prepareBookingEdit(row) {
    setEditingBookingId(row.id);
    setBookingForm({
      stay_date: row.stay_date || todayISO(),
      room_number: row.room_number || '',
      guest_name: row.guest_name || '',
      guest_label: row.guest_label || '',
      arrival_date: row.arrival_date || '',
      departure_date: row.departure_date || '',
      booking_status: row.booking_status || 'in_house',
      beds24_booking_id: row.beds24_booking_id || '',
      source: row.source || 'manual_snapshot',
      notes: row.notes || '',
    });
  }

  const selectedMeta = roomChargeStatusMeta(selected?.posting_status);

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Room Charge Queue</h1>
            <p className="muted">Front desk can move each charge from pending, to posted, to settled with clear status, dispute review, and guest folio context.</p>
          </div>
          <div className="row wrap">
            <span className="badge warn">Pending: {summary.pending_frontdesk_post}</span>
            <span className="badge info">Posted: {summary.posted_to_beds24}</span>
            <span className="badge success">Settled: {summary.settled_at_frontdesk}</span>
            {!!summary.attention && <span className="badge danger">Needs review: {summary.attention}</span>}
            {loading && <span className="badge info">Loading…</span>}
          </div>
        </div>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <div className="card-grid" style={{ marginBottom: 14 }}>
          {STATUS_VIEWS.map((view) => {
            const countMap = {
              all: summary.all,
              pending_frontdesk_post: summary.pending_frontdesk_post,
              posted_to_beds24: summary.posted_to_beds24,
              settled_at_frontdesk: summary.settled_at_frontdesk,
              attention: summary.attention,
            };
            const toneMap = { all: 'info', pending_frontdesk_post: 'warn', posted_to_beds24: 'info', settled_at_frontdesk: 'success', attention: 'danger' };
            return (
              <button
                key={view.key}
                type="button"
                className={`summary-card-button ${filters.view === view.key ? 'active' : ''}`}
                onClick={() => setFilters((prev) => ({ ...prev, view: view.key }))}
              >
                <span className={`badge ${toneMap[view.key]}`}>{view.label}</span>
                <strong>{countMap[view.key] || 0}</strong>
                <span className="small muted">{view.key === 'all' ? 'Visible for stay date' : `${view.label} items`}</span>
              </button>
            );
          })}
        </div>

        <div className="form-grid room-charge-filter-grid">
          <label className="field">
            Stay Date
            <input type="date" value={filters.stay_date} onChange={(e) => setFilters((prev) => ({ ...prev, stay_date: e.target.value }))} />
          </label>
          <label className="field">
            Search
            <input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder="Room, guest, Beds24 ref, bill-to" />
          </label>
          <div className="row wrap align-end">
            <button type="button" className="secondary" onClick={() => loadData()}>Refresh</button>
            <span className="small muted">{queueRows.length} rows in view</span>
          </div>
        </div>

        <div className="two-column-layout" style={{ marginTop: 14 }}>
          <div className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <div>
                <strong>{filters.view === 'all' ? 'Posting Queue' : `${STATUS_VIEWS.find((view) => view.key === filters.view)?.label || 'Queue'} Screen`}</strong>
                <div className="small muted">Clearer pending vs posted vs settled front-desk list</div>
              </div>
              <span className="small muted">{queueRows.length} results</span>
            </div>
            <div className="stack-tight" style={{ marginTop: 10 }}>
              {queueRows.map((row) => {
                const meta = roomChargeStatusMeta(row.posting_status);
                return (
                  <button
                    key={row.id}
                    type="button"
                    className={`list-row-button queue-card-button ${selected?.id === row.id ? 'active' : ''}`}
                    onClick={() => selectQueueRow(row)}
                  >
                    <div>
                      <div className="row wrap" style={{ gap: 8 }}>
                        <strong>{row.room_number || '-'}</strong>
                        <span>{row.guest_label || 'Guest'}</span>
                        <span className={`badge ${meta.tone}`}>{meta.label}</span>
                      </div>
                      <div className="small muted">{row.order_no || '-'} · {row.service_type || '-'} · {row.booking_date || '-'}</div>
                      <div className="small muted">{row.beds24_posting_reference || row.bill_to || row.later_payment_status || 'Awaiting front-desk action'}</div>
                    </div>
                    <div className="text-right">
                      <strong>{money(row.charge_amount)}</strong>
                      <div className="small muted">{row.order_source || '-'}</div>
                    </div>
                  </button>
                );
              })}
              {!queueRows.length && <div className="muted">No room charges found for this date and filter.</div>}
            </div>
          </div>

          <div className="card">
            {!selected && <div className="muted">Select a room charge from the queue.</div>}
            {!!selected && (
              <div className="stack-tight">
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <strong>{selected.room_number} · {selected.guest_label || 'Guest'}</strong>
                    <div className="small muted">Order {selected.order_no || '-'} · {selected.service_type || '-'} · {selected.order_source || '-'}</div>
                  </div>
                  <span className={`badge ${selectedMeta.tone}`}>{selectedMeta.label}</span>
                </div>

                <div className="status-rail">
                  <div className={`status-rail-step ${['pending_frontdesk_post', 'posted_to_beds24', 'settled_at_frontdesk'].includes(selected.posting_status) ? 'active' : ''}`}>Pending</div>
                  <div className={`status-rail-step ${['posted_to_beds24', 'settled_at_frontdesk'].includes(selected.posting_status) ? 'active' : ''}`}>Posted</div>
                  <div className={`status-rail-step ${selected.posting_status === 'settled_at_frontdesk' ? 'active' : ''}`}>Settled</div>
                  {['rejected', 'disputed', 'written_off', 'cancelled'].includes(String(selected.posting_status || '').toLowerCase()) && <div className="status-rail-step danger active">Exception</div>}
                </div>

                <div className="form-grid-3">
                  <div className="card"><div className="muted">Amount</div><strong>{money(selected.charge_amount)}</strong></div>
                  <div className="card"><div className="muted">Service</div><strong>{selected.service_date || '-'}</strong><div className="small muted">{selected.service_time || '-'}</div></div>
                  <div className="card"><div className="muted">Payment date</div><strong>{selected.payment_date || '-'}</strong></div>
                </div>
                <div className="form-grid-3">
                  <div className="card"><div className="muted">Beds24 booking</div><strong>{selected.beds24_booking_id || '-'}</strong></div>
                  <div className="card"><div className="muted">Posting ref</div><strong>{selected.beds24_posting_reference || '-'}</strong></div>
                  <div className="card"><div className="muted">Bill to</div><strong>{selected.bill_to || '-'}</strong></div>
                </div>

                <div className="card">
                  <strong>Order Context</strong>
                  <div className="small muted" style={{ marginTop: 8 }}>
                    <div>Order: {selected.order_no || '-'}</div>
                    <div>Guest: {selected.guest_name || '-'}</div>
                    <div>Table: {selected.table_label || '-'}</div>
                    <div>Note: {selected.order_note || '-'}</div>
                  </div>
                </div>

                <form className="form-stack" onSubmit={handleStatusSubmit}>
                  <div className="form-grid">
                    <label className="field">
                      New Status
                      <select value={statusForm.posting_status} onChange={(e) => setStatusForm((prev) => ({ ...prev, posting_status: e.target.value }))}>
                        {STATUS_OPTIONS.filter(Boolean).map((status) => <option key={status} value={status}>{roomChargeStatusMeta(status).label}</option>)}
                      </select>
                    </label>
                    <label className="field">
                      Beds24 Posting Reference
                      <input value={statusForm.beds24_posting_reference} onChange={(e) => setStatusForm((prev) => ({ ...prev, beds24_posting_reference: e.target.value }))} placeholder="Invoice note / manual reference" />
                    </label>
                    <label className="field">
                      Later Payment Status
                      <input value={statusForm.later_payment_status} onChange={(e) => setStatusForm((prev) => ({ ...prev, later_payment_status: e.target.value }))} placeholder="pending / settled / disputed" />
                    </label>
                    <label className="field">
                      Payment Date
                      <input type="date" value={statusForm.payment_date} onChange={(e) => setStatusForm((prev) => ({ ...prev, payment_date: e.target.value }))} />
                    </label>
                    <label className="field">
                      Bill To
                      <input value={statusForm.bill_to} onChange={(e) => setStatusForm((prev) => ({ ...prev, bill_to: e.target.value }))} placeholder="guest / company / event organizer" />
                    </label>
                    <label className="field">
                      Rejected Reason
                      <input value={statusForm.rejected_reason} onChange={(e) => setStatusForm((prev) => ({ ...prev, rejected_reason: e.target.value }))} placeholder="Only if rejected" />
                    </label>
                  </div>
                  <label className="field">
                    Posting Note
                    <textarea value={statusForm.note} onChange={(e) => setStatusForm((prev) => ({ ...prev, note: e.target.value }))} placeholder="Front-desk note, posting detail, or follow-up" />
                  </label>
                  <label className="field">
                    Dispute Note
                    <textarea value={statusForm.dispute_note} onChange={(e) => setStatusForm((prev) => ({ ...prev, dispute_note: e.target.value }))} placeholder="Explain any guest dispute or mismatch" />
                  </label>
                  <div className="row wrap">
                    <button type="submit" className="primary">Update Status</button>
                    <button type="button" className="secondary" onClick={() => setStatusForm((prev) => ({ ...prev, posting_status: 'posted_to_beds24' }))}>Mark as Posted</button>
                    <button type="button" className="secondary" onClick={() => setStatusForm((prev) => ({ ...prev, posting_status: 'settled_at_frontdesk' }))}>Mark as Settled</button>
                    <button type="button" className="secondary" onClick={() => setStatusForm((prev) => ({ ...prev, posting_status: 'disputed' }))}>Flag as Disputed</button>
                  </div>
                </form>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="toolbar">
          <div>
            <h2>In-House Booking Snapshot</h2>
            <p className="muted">Cleaner picker for café and front-desk teams when the live PMS lookup is not available.</p>
          </div>
          <div className="row wrap">
            <input value={bookingSearch} onChange={(e) => setBookingSearch(e.target.value)} placeholder="Search room / guest / Beds24 ID" />
            <span className="small muted">{filteredBookings.length} matches</span>
          </div>
        </div>

        <div className="two-column-layout" style={{ marginTop: 14 }}>
          <form className="card form-stack" onSubmit={handleBookingSubmit}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>{editingBookingId ? 'Edit' : 'Add'} Snapshot Booking</strong>
              {editingBookingId && <button type="button" className="secondary" onClick={() => { setBookingForm(emptyBooking); setEditingBookingId(null); }}>Cancel Edit</button>}
            </div>
            <div className="form-grid">
              <label className="field">Stay Date<input type="date" value={bookingForm.stay_date} onChange={(e) => setBookingForm((prev) => ({ ...prev, stay_date: e.target.value }))} /></label>
              <label className="field">Room Number<input value={bookingForm.room_number} onChange={(e) => setBookingForm((prev) => ({ ...prev, room_number: e.target.value }))} placeholder="201" /></label>
              <label className="field">Guest Name<input value={bookingForm.guest_name} onChange={(e) => setBookingForm((prev) => ({ ...prev, guest_name: e.target.value }))} /></label>
              <label className="field">Guest Label<input value={bookingForm.guest_label} onChange={(e) => setBookingForm((prev) => ({ ...prev, guest_label: e.target.value }))} placeholder="Rm 201 · John Santos" /></label>
            </div>
            <details>
              <summary style={{ cursor: 'pointer', marginBottom: 10 }}>Optional Details</summary>
              <div className="form-grid">
                <label className="field">Arrival<input type="date" value={bookingForm.arrival_date} onChange={(e) => setBookingForm((prev) => ({ ...prev, arrival_date: e.target.value }))} /></label>
                <label className="field">Departure<input type="date" value={bookingForm.departure_date} onChange={(e) => setBookingForm((prev) => ({ ...prev, departure_date: e.target.value }))} /></label>
                <label className="field">Booking Status<input value={bookingForm.booking_status} onChange={(e) => setBookingForm((prev) => ({ ...prev, booking_status: e.target.value }))} /></label>
                <label className="field">Beds24 Booking ID<input value={bookingForm.beds24_booking_id} onChange={(e) => setBookingForm((prev) => ({ ...prev, beds24_booking_id: e.target.value }))} /></label>
                <label className="field">Source<input value={bookingForm.source} onChange={(e) => setBookingForm((prev) => ({ ...prev, source: e.target.value }))} /></label>
              </div>
              <label className="field">Notes<textarea value={bookingForm.notes} onChange={(e) => setBookingForm((prev) => ({ ...prev, notes: e.target.value }))} /></label>
            </details>
            <div className="row wrap"><button type="submit" className="primary">{editingBookingId ? 'Update Snapshot' : 'Add Snapshot'}</button></div>
          </form>

          <div className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>Snapshot Bookings for {filters.stay_date || todayISO()}</strong>
              <span className="small muted">Picker source</span>
            </div>
            <div className="stack-tight" style={{ marginTop: 10 }}>
              {filteredBookings.map((row) => (
                <div key={row.id} className="list-row booking-picker-row">
                  <div>
                    <div className="row wrap" style={{ gap: 8 }}>
                      <strong>{row.room_number}</strong>
                      <span>{row.guest_label || row.guest_name || 'Guest'}</span>
                      <span className={`badge ${String(row.booking_status || '').toLowerCase() === 'in_house' ? 'success' : 'info'}`}>{row.booking_status || 'snapshot'}</span>
                    </div>
                    <div className="small muted">{row.arrival_date || '-'} to {row.departure_date || '-'} · Beds24 ID: {row.beds24_booking_id || '-'}</div>
                  </div>
                  <button type="button" className="secondary" onClick={() => prepareBookingEdit(row)}>Edit</button>
                </div>
              ))}
              {!filteredBookings.length && <div className="muted">No snapshot bookings saved for this date yet.</div>}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
