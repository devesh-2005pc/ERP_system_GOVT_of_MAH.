# Architecture

## 1. Audit of the original ZIP (`mudranalaya-erp-mis-1.zip`)

The ZIP contained three copies of the same app (~1,500 lines total):

| Folder | What it was |
|---|---|
| `erp-app/` | Plain Node.js `http` server (no framework) + vanilla JS frontend |
| `erp-desktop/` | The same app wrapped in Electron |
| `erp-mobile/` | The same frontend wrapped in Capacitor, with **no backend** - writes straight to `localStorage` |

**Data layer (`db.js`):** generic CRUD over 17 untyped "collections"
(`inventory_items`, `stock_transactions`, `materials`, `production_jobs`,
`bills`, `vendors`, `employees`, `payroll`, etc). Tries MongoDB first, falls
back to a local JSON file with a "pending sync" queue replayed on
reconnect - explicitly last-write-wins, no conflict detection, per the
project's own README.

**API (`server.js`):** one generic router,
`GET/POST/PUT/DELETE /api/:collection[/:id]` - any authenticated (there was
no authentication) client could read or write any collection, including
directly setting a stock quantity to any client-supplied number.

**The one genuinely valuable piece of business logic:** `computeEstimate()`,
a three-formula (Fixed / Variable / Billing) DTP → proof → CTP → printing →
binding → dispatch → depot cost calculator with an editable rate master.
This has been ported into `app/api/routers/costing.py::compute_estimate()`,
rewritten in `Decimal` (the original used floating point) with the same
formula structure.

**What was missing entirely** (confirmed by the project's own README):
authentication, roles/permissions, audit trail, transaction integrity on
stock changes (no locking, no ledger - just an overwritten number),
reporting, forecasting, license/device activation, backups, and CORS was
wide open (`Access-Control-Allow-Origin: *`).

**Decision:** everything in sections 6-38 of the brief needed to be built
from scratch. What was carried forward: the costing formula, the vocabulary
of "collections" as a starting point for the new normalized schema, and the
general department list implied by the UI.

## 2. Why FastAPI + PostgreSQL + SQLAlchemy

- **Security first:** the original app's single biggest problem was zero
  authorization enforcement. FastAPI's dependency-injection system lets
  every route declare *exactly* which departments may call it
  (`app/auth/deps.py::require_departments`), and that's checked before any
  handler code runs - it can't be bypassed by calling the API directly.
- **Data integrity:** PostgreSQL row locking (`SELECT ... FOR UPDATE`) is
  required to make concurrent stock transactions safe across multiple
  office workstations hitting the same central server - a plain JSON file
  or MongoDB-without-transactions can't give this guarantee.
- **Simplicity:** SQLAlchemy + Pydantic gives one typed, validated model per
  entity instead of untyped dictionaries in arbitrary "collections."
- The frontend deliberately stays as **plain HTML/CSS/JS** (no React/build
  step): the brief explicitly says not to introduce technology for its own
  sake, and an office ERP with `<button onclick>` forms doesn't need a
  bundler. It's genuinely simpler to package into one executable this way,
  too - the frontend is just static files served by the same FastAPI app.

## 3. System architecture

```
                    CENTRAL OFFICE SERVER
                   (one Windows PC or a server)
                 Mudranalaya.exe (FastAPI + Uvicorn)
                              |
                        PostgreSQL
                              |
                 WebSocket + REST API (LAN)
        +----------+----------+----------+----------+
        |          |          |          |          |
     STORE PC  PLANNING PC DISPATCH PC ACCOUNTS PC MANAGER PC
    (browser)   (browser)  (browser)  (browser)   (browser)
```

Every workstation is a thin browser client talking to one central server
over the office LAN. There are no per-workstation databases and no
peer-to-peer sync to reason about - the server is the single source of
truth, which is what section 4 of the brief asks for ("do not blindly
preserve the old MongoDB+JSON-fallback architecture").

**Offline behaviour:** the brief calls for careful design here rather than
copying the old fallback. This build takes the position that an ERP
recording real inventory transactions must not let two disconnected
machines independently "guess" at stock and reconcile later - that's
exactly the class of bug the old JSON-fallback design was vulnerable to.
Instead:
- The client is a thin browser view with no local write queue; if it loses
  the connection to the server, actions simply fail with a clear "cannot
  reach server" error rather than silently queuing.
- Every state-changing request carries an optional `idempotency_key` (see
  `app/services/inventory.py`), so if a workstation's request timed out but
  actually succeeded server-side, a client retry is safely deduplicated
  instead of double-applying.
- This is a deliberate trade-off: a queued-writes-while-offline model was
  considered and rejected for the inventory hot path specifically, because
  reconciling two offline stock edits correctly needs either operational
  transforms or a human review step, which was out of scope to build
  reliably in this pass. If true offline queuing becomes a requirement, the
  `idempotency_key` and audit-log infrastructure already here is the
  correct foundation to add it to.

## 4. Real-time architecture

`app/ws/manager.py` keeps an in-memory registry of connected WebSocket
clients tagged by department. `app/api/routers/ws_routes.py` authenticates
the connection with the same JWT used for REST calls. Business logic
(inventory, requests, purchasing, production, dispatch, accounts routers)
calls `manager.broadcast(event_type, payload, visible_to_departments=...)`
after a successful DB commit - so a broadcast never fires for a change that
didn't actually happen, and it's filtered so Store's stock update isn't
pushed to Dispatch's browser tab.

## 5. Forecasting architecture

`app/api/routers/forecasting.py` implements a moving-average forecast over
real `InventoryTransaction` (ISSUE) rows, honestly reporting
`"Insufficient historical data for reliable forecast."` when fewer than 3
months of data exist, per the brief's explicit instruction not to fake
ML/AI accuracy. Once enough data exists it computes predicted monthly
demand, a variability-based safety stock, reorder point, expected shortage
date, and a LOW/MEDIUM/HIGH confidence label based on data volume and
coefficient of variation - all interpretable arithmetic, no black box.

## 6. What's built vs. what remains (honesty check, per the brief's section 43)

**Built and verified (see `backend/tests/`, 38 passing tests, and the
manual end-to-end runs described in the delivery notes):**
auth + RBAC + department isolation, materials/inventory with row-locked
atomic transactions, the full material request → approval → fulfillment
workflow with real stock movement, suppliers/purchase orders/goods
receipts, production jobs with GREEN/RED material availability, dispatch,
accounts/budgets with a real budget-utilization alert, the costing engine,
audit logging, notifications, a department-scoped dashboard, WebSocket
real-time events, honest forecasting, RSA-signed license/device
activation, a working frontend for every module, and a PyInstaller build
that was tested end-to-end in this environment (producing a working Linux
binary, since a Windows `.exe` can only be *built* on Windows - see
`DEPLOYMENT.md`).

**Not done / explicitly out of scope for this pass:**
- Alembic migration scripts (the app currently uses `create_all` for schema
  setup; fine for a first deployment, but schema *changes* to an existing
  production database should go through Alembic, which isn't wired up yet).
- File/document upload for invoices, dispatch proofs, etc. (section 27) -
  the config for upload validation exists (`UPLOAD_DIR`,
  `ALLOWED_UPLOAD_EXTENSIONS`) but no upload endpoint was built.
- PDF export for reports (Excel/CSV export is implemented and tested; PDF
  via `reportlab` is installed as a dependency but not wired to an endpoint).
  Scheduled/automatic backups on a timer (the backup/restore *scripts* work
  and were tested, but nothing runs them automatically - use Windows Task
  Scheduler, documented in `DEPLOYMENT.md`).
- A hosted license-issuing service (the cryptography, device fingerprinting,
  and verification are real and tested; issuing a license is a
  command-line tool run by the vendor, not a running server, per the
  brief's own instruction that the private key must never be deployed
  anywhere near an office machine).
