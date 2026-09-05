import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const sessions = readFileSync(new URL('../app/sessions/page.js', import.meta.url), 'utf8');
const cashMovements = readFileSync(new URL('../app/cash-movements/page.js', import.meta.url), 'utf8');
const pos = readFileSync(new URL('../app/pos/page.js', import.meta.url), 'utf8');
const users = readFileSync(new URL('../app/users/page.js', import.meta.url), 'utf8');
const roomCharges = readFileSync(new URL('../app/room-charges/page.js', import.meta.url), 'utf8');

test('session close stays blocked until sign-off and variance requirements are complete', () => {
  assert.match(sessions, /closeSignOffComplete/);
  assert.match(sessions, /closeVarianceExplained/);
  assert.match(sessions, /disabled=\{!canCloseSelectedSession\}/);
  assert.match(sessions, /required=\{Math\.abs\(selectedCloseVariance\) > 0\.009\}/);
});

test('cash movement form exposes native requirements and blocks incomplete records', () => {
  assert.match(cashMovements, /const approvalRequired = isTransfer \|\| form\.movement_type === 'owner_withdrawal'/);
  assert.match(cashMovements, /disabled=\{approvalRequired\}/);
  assert.match(cashMovements, /disabled=\{!canSubmit\}/);
  assert.match(cashMovements, /required=\{form\.direction === 'out'\}/);
});

test('cashier header groups statuses and actions so tools do not wrap alone', () => {
  assert.match(pos, /className="pos-status-cluster"/);
  assert.match(pos, /className="pos-top-actions"/);
  assert.match(pos, /className="pos-tools-menu"/);
  assert.match(pos, /className="terminal-exit-link"/);
  assert.match(pos, /className="local-only-ribbon">Local only/);
  assert.match(pos, /No safe or bank destination is available/);
});

test('user creation requires credentials and always retains the primary role', () => {
  assert.match(users, /const canSaveUser/);
  assert.match(users, /disabled=\{!canSaveUser\}/);
  assert.match(users, /required=\{!form\.id\}/);
  assert.match(users, /row\.id === primaryRoleId/);
});

test('manual room booking cannot save without a stay date and room number', () => {
  assert.match(roomCharges, /const canSaveBooking/);
  assert.match(roomCharges, /disabled=\{!canSaveBooking\}/);
  assert.match(roomCharges, /Room Number<input required/);
});
