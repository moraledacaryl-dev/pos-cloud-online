import test from "node:test";
import assert from "node:assert/strict";
import {
  applyKeypadInput,
  findRoomChargeBookingMatches,
  rankCatalogItems,
  roomChargeStatusMeta,
  summarizeOutboxRows,
  summarizeRoomChargeQueue,
} from "../lib/ui_contracts.mjs";

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
  ]);
  assert.equal(summary.pending, 1);
  assert.equal(summary.failed, 1);
  assert.equal(summary.synced, 1);
  assert.equal(summary.retrying, 1);
});

test("room charge status metadata exposes display tone", () => {
  assert.deepEqual(roomChargeStatusMeta('settled_at_frontdesk'), { tone: 'success', label: 'Settled' });
});
