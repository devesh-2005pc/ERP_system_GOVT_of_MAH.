# Security

## Authentication

- Passwords hashed with **Argon2id** (`app/auth/security.py`, via
  `argon2-cffi`), never stored or logged in plaintext.
- JWT **access tokens** (short-lived, 30 min default) plus a
  server-side-revocable **refresh session** (`refresh_sessions` table) - so
  logout, an idle timeout, or an admin action actually invalidates a
  session, unlike a purely stateless JWT scheme.
- Account lockout after 5 failed logins (15 minutes), login history
  recorded per attempt (`login_history` table), tested in
  `tests/test_auth.py::test_account_lockout_after_repeated_failures`.
- New accounts are created with `must_change_password=True`.

## Authorization / department data isolation

This is enforced **only** at the backend dependency layer - never by hiding
UI buttons - so a Store user calling a Dispatch endpoint directly (e.g. with
curl or a modified request) gets `403 Forbidden`, not filtered/empty data.

- `app/auth/deps.py::require_departments(*allowed)` is a dependency factory
  used on every router. It always allows `MANAGER` and `SUB_ADMIN`
  (`CROSS_DEPARTMENT_ROLES`) in addition to whatever departments are named
  explicitly - this is the single place implementing "only Manager and
  Sub-Admin can see/edit every department's data."
- `require_manager` / `require_manager_or_subadmin` guard the most
  sensitive actions (deactivating a user, changing costing rates, revoking
  a device).
- The one deliberate exception: the materials **catalog** (name, SKU,
  current stock headline) is readable by every department, because Planning
  must be able to check material availability before scheduling a job
  (spec section 11) - but the detailed inventory **ledger**
  (`/api/inventory/transactions`) stays Store/Manager/Sub-Admin-only.
- Verified by `tests/test_rbac.py` (13 tests): Dispatch can't see purchase
  orders or budgets, Planning can't see Accounts or Dispatch data, Employees
  have no department-wide access at all, and Manager/Sub-Admin can reach
  every department's endpoints.

## Inventory concurrency safety

See `DATABASE.md` for the ledger design. `apply_stock_transaction()` uses
`SELECT ... FOR UPDATE` row locking (real on PostgreSQL; SQLite serializes
writes at the file level, sufficient for the automated tests but PostgreSQL
is required for true concurrent-process locking in a real multi-workstation
deployment) plus an `idempotency_key` to make client retries safe.
Confirmed with an actual concurrency test that fires 30 simultaneous issue
requests against one material via a thread pool and asserts the final stock
matches arithmetic exactly (`tests/test_inventory.py`).

## Input validation

All request bodies are validated by Pydantic schemas server-side (never
trusting client-side validation alone). Quantities are constrained to be
positive; SKUs and employee IDs are enforced unique at the database level
(`unique=True` constraints, not just application checks).

## Error handling

A global exception handler (`app/main.py`) ensures unhandled exceptions
return a generic `"An unexpected error occurred"` to the client and log the
full stack trace server-side only - no stack traces or internal details
ever reach the browser.

## Headers & CORS

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer` are set on every response. CORS origins are
an explicit allow-list from `CORS_ALLOWED_ORIGINS` (office LAN URLs) -
**never** `Access-Control-Allow-Origin: *`, which was the original ZIP's
configuration.

## Secrets

No secrets are hardcoded anywhere in the codebase. `JWT_SECRET_KEY`,
`DATABASE_URL`, and all other configuration come from environment
variables (`.env`, never committed - see `.env.example`). The application
**refuses to start** in `ENVIRONMENT=production` if `JWT_SECRET_KEY` is
still the development default (`app/main.py::on_startup`).

## License / device activation

Real RSA-3072 PSS-signed tokens (`app/licensing/tokens.py`, using the
`cryptography` library):
- The **private** signing key is generated once
  (`scripts/generate_license_keys.py`) and is never imported by the shipped
  application - only `scripts/issue_license.py` (an offline vendor tool)
  uses it.
- The shipped app only ever loads the **public** key
  (`app/licensing/service.py`) to verify a license token's signature,
  expiry, and device-fingerprint binding. It cannot mint or extend a
  license.
- Device fingerprint combines computer name, OS/machine info, a
  MAC-derived node ID, and (on Windows) the registry `MachineGuid`
  (`app/licensing/fingerprint.py`).
- Verified with real cryptographic tests
  (`tests/test_licensing.py`): a tampered payload, a token signed by the
  wrong key, an expired token, and a wrong-device token are all correctly
  rejected.
- As stated plainly in the brief itself: **client-side protection can never
  be absolute.** This design raises the bar substantially (a valid license
  cannot be forged or extended without the private key, which never leaves
  the vendor's machine) without pretending to be unbreakable.

## Known limitations (see also `ARCHITECTURE.md`)

- No file upload endpoint yet, so the "insecure upload" hardening in the
  brief (extension/size/path-traversal checks) is scaffolded in config
  (`UPLOAD_DIR`, `ALLOWED_UPLOAD_EXTENSIONS`, `MAX_UPLOAD_MB`) but not yet
  attached to a real endpoint - do not assume file upload is safe until
  that endpoint is built and reviewed.
- MFA fields exist on the `User` model but the login flow doesn't enforce
  MFA yet.
