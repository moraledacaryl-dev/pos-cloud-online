import test from "node:test";
import assert from "node:assert/strict";
import {
  applyKeypadInput,
  findRoomChargeBookingMatches,
  explainSyncError,
  rankCatalogItems,
  roomChargeStatusMeta,
  summarizeTerminalHealth,
  summarizeOutboxRows,
  summarizeRoomChargeQueue,
} from "../lib/ui_contracts.mjs";
import { filterRecipeDishes, MAX_RECIPE_PDF_BYTES, validateRecipePdfFile } from "../lib/recipeLibrary.mjs";

test("catalog ranking prefers exact SKU and tight name matches", () => {
  const ranked = rankCatalogItems([
    { display_name: 'Clubhouse Sandwich', sku_code: 'FOOD-001', category_name: 'Meals' },
    { display_name: 'Iced Coffee', sku_code: 'DRINK-001', category_name: 'Beverages' },
    { display_name: 'Club Soda', sku_code: 'CLUB-123', category_name: 'Beverages' },
  ], { query: 'club', category: 'All' });
  assert.equal(ranked[0].display_name, 'Club Soda');
  assert.equal(ranked[1].display_name, 'Clubhouse Sandwich');
});

test("keypad input keeps money format sane", () => {
  assert.equal(applyKeypadInput('', '1'), '1');
  assert.equal(applyKeypadInput('1', '.'), '1.');
  assert.equal(applyKeypadInput('1.', '2'), '1.2');
  assert.equal(applyKeypadInput('1.23', '4'), '1.23');
  assert.equal(applyKeypadInput('120', 'backspace'), '12');
  assert.equal(applyKeypadInput('120', 'clear'), '');
});

test("room charge booking matches surface strongest candidates first", () => {
  const matches = findRoomChargeBookingMatches([
    { id: 1, stay_date: '2026-04-20', room_number: '201', guest_label: 'Juan Santos', booking_status: 'in_house' },
    { id: 2, stay_date: '2026-04-20', room_number: '305', guest_label: 'Maria Cruz', booking_status: 'in_house' },
  ], { stayDate: '2026-04-20', roomNumber: '201', guestName: 'Juan' });
  assert.equal(matches[0].id, 1);
});

test("room charge queue summary separates pending posted settled and attention", () => {
  const summary = summarizeRoomChargeQueue([
    { posting_status: 'pending_frontdesk_post' },
    { posting_status: 'posted_to_beds24' },
    { posting_status: 'settled_at_frontdesk' },
    { posting_status: 'disputed' },
  ]);
  assert.deepEqual(summary, {
    all: 4,
    pending_frontdesk_post: 1,
    posted_to_beds24: 1,
    settled_at_frontdesk: 1,
    attention: 1,
  });
});

test("outbox summary counts retries separately from status totals", () => {
  const summary = summarizeOutboxRows([
    { status: 'pending', retry_count: 0 },
    { status: 'failed', retry_count: 2 },
    { status: 'synced', retry_count: 1 },
    { status: 'suppressed', retry_count: 3 },
  ]);
  assert.equal(summary.pending, 1);
  assert.equal(summary.failed, 1);
  assert.equal(summary.synced, 1);
  assert.equal(summary.suppressed, 1);
  assert.equal(summary.retrying, 1);
});

test("sync error explanations give manager recovery actions", () => {
  assert.match(
    explainSyncError({ event_type: 'room_charge.request_created', last_error: 'Original receivable for reversal was not found' }).action,
    /original room charge synced first/i,
  );
  assert.match(
    explainSyncError({ event_type: 'payment.collected', last_error: '401 unauthorized invalid token' }).summary,
    /credentials/i,
  );
  assert.match(
    explainSyncError({ event_type: 'order.finalized', last_error: 'Event type is disabled' }).action,
    /enable this sync type/i,
  );
  assert.match(
    explainSyncError({ event_type: 'cash_movement.created', last_error: 'ECONNREFUSED connection timeout' }).summary,
    /unreachable/i,
  );
});

test("terminal health summary prioritizes offline and blocked sync states", () => {
  assert.deepEqual(
    summarizeTerminalHealth(null, { online: false, offlineDraftsCount: 2 }).tone,
    'warn',
  );
  const blocked = summarizeTerminalHealth({
    database: { ok: true, migration: { requires_upgrade: false } },
    accounting_api: { ok: true },
    sync_worker: { is_stale: false },
    outbox: { failed: 0, blocked: 1, due_now: 0 },
  }, { online: true });
  assert.equal(blocked.tone, 'danger');
  assert.match(blocked.action, /Sync Queue/i);
});

test("room charge status metadata exposes display tone", () => {
  assert.deepEqual(roomChargeStatusMeta('settled_at_frontdesk'), { tone: 'success', label: 'Settled' });
});

test("recipe dishes filter by PDF status without duplicating accounting variants", () => {
  const rows = filterRecipeDishes([
    { external_menu_item_id: 1, dish_name: 'Iced Coffee', category_name: 'Beverages', variants: ['Regular', 'Large'], recipe: { id: 10 } },
    { external_menu_item_id: 2, dish_name: 'Club Sandwich', category_name: 'Meals', variants: [], recipe: null },
  ], { q: 'large', category: 'Beverages', status: 'with_pdf' });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].dish_name, 'Iced Coffee');
});

test("recipe upload validation accepts PDFs and rejects wrong or oversized files", () => {
  assert.equal(validateRecipePdfFile({ name: 'recipe.pdf', type: 'application/pdf', size: 1024 }), '');
  assert.match(validateRecipePdfFile({ name: 'recipe.txt', type: 'text/plain', size: 1024 }), /PDF/);
  assert.match(validateRecipePdfFile({ name: 'large.pdf', type: 'application/pdf', size: MAX_RECIPE_PDF_BYTES + 1 }), /15 MB/);
});
