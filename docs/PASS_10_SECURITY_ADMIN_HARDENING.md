# Pass 10 — Security, Permissions, and Audit Hardening

## Scope

Pass 10 closes privilege-escalation and accountability gaps in POS user administration.

## Controls

- `users.manage` alone cannot grant legacy `owner` / `admin` access.
- `users.manage` alone cannot attach the canonical Owner RBAC role.
- Non-owner administrators cannot reset, deactivate, or re-authorize an existing owner/admin account.
- Users cannot deactivate themselves through user administration.
- Users cannot change their own role or RBAC assignments through user administration.
- Existing owner/admin users retain authority to administer privileged accounts.
- User creation, user update, force logout, and self session revocation are written to the POS audit log.
- Password values are never serialized into security audit details; only `password_changed=true` is recorded.

## Defense in depth

Endpoint permission dependencies remain authoritative. Effective permissions are still resolved server-side for every request. Session-version revocation continues to invalidate credentials after password changes, deactivation, force logout, or logout-all.

## Deployment

No database migration is required. Deploy the backend and restart `pos-backend`. The frontend and sync worker can remain on the same commit without a rebuild because this pass has no frontend code changes.
