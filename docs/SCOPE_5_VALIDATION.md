Scope 5 cashier-terminal upgrade applied on top of scope 1-4.

Added in this package:
- product search retained and keyboard focus shortcut added
- barcode quick-add retained and polished
- modifiers / add-ons / bundle pairings in POS terminal via product profile builder
- required modifier groups in POS builder
- quick quantity keypad in cart
- note prompt support in configurator and line editor
- table map style selector in terminal
- customer display HTML page fed by localStorage from terminal
- receipt print helper and reprint-last-receipt support
- touch payment keypad and larger due/applied/change displays
- promotion engine suggestions with apply/clear flow
- manager override modal for discount approval in POS
- manager override modal for order voids in Orders page

Files added:
- frontend/lib/terminalProfiles.js
- frontend/lib/receipt.js
- frontend/components/ManagerOverrideModal.js
- frontend/public/customer-display.html
- docs/SCOPE_5_VALIDATION.md

Files upgraded:
- frontend/app/pos/page.js
- frontend/app/orders/page.js
- frontend/app/globals.css

Preservation check:
- no original backend files were removed
- no original top-level repo files were removed
- original repo structure remains intact and this zip is an additive upgrade

Validation performed here:
- balanced bracket count check on upgraded POS and Orders pages
- import path existence check for all newly added frontend files

Not claimed in this scope:
- no new backend APIs were required for this item-5-only pass
- no full Next.js production build was executed in-container
