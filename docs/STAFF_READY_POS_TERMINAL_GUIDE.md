# Staff Ready POS Terminal Guide

## Pilot Day Flow

Run this once before full staff rollout.

1. Log in with a cashier account and confirm the app opens directly to POS.
2. Select or open the correct register session.
3. Start an order from a service area table.
4. Start another order with **Start Order First**, add items, then assign a table.
5. Hold an order, restore it from the service queue, add another item, then pay.
6. Take a cash payment and print the receipt.
7. Take a split payment using cash plus card or GCash.
8. Take a room charge only after selecting or typing room/guest context.
9. Disconnect network briefly, add a cart, and use **Save Offline Draft**.
10. Reconnect, restore the offline draft, review it, then save or pay.
11. Save a money drop and a paid-out/expense.
12. Close the session with denominations, sign-off, and print the close packet.
13. Open Sync Queue diagnostics and confirm no critical failed or blocked events remain.
14. Confirm Accounting receives expected room charges, payments, cash movement, and session close events.

## Terminal Status Badges

- **Ready**: POS server, Accounting connection, sync worker, and queue are healthy.
- **Watch**: Service can continue, but staff should clear warnings during a quiet moment.
- **Manager review**: Manager should open Sync Queue before closing, room-charge posting, or end-of-day review.
- **Offline draft mode**: Staff may preserve order details locally, but must not take payment, post room charges, close sessions, refund, or create cash movements.

## Offline Draft Rules

Offline drafts are local to the same browser and device.

- Use **Save Offline Draft** before leaving the screen while offline.
- Restore drafts only after POS is online again.
- Review session, table, guest, items, notes, and tender before saving or paying.
- Do not collect payment until the server confirms the order and payment.
- If a guest already paid during an outage by an external terminal, record the payment only after the order is restored and the manager confirms the reference.

## Close Packet

At close, the cashier should enter denominations and sign-off details.

- If variance is not zero, enter a variance note or close note.
- Print the close packet and attach cash count, drops, paid-out receipts, and manager handover notes.
- If the browser blocks the first print window, use **Print Close Packet** from the preview modal.
