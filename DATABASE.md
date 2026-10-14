# Database

PostgreSQL in production; SQLite for local development (same schema, same
SQLAlchemy models - `app/core/database.py` picks the engine from
`DATABASE_URL`). All primary keys are UUIDs (stored as CHAR(36) via the
custom `GUID` type in `app/models/base.py` so the schema is identical on
both backends). Every table has `created_at`/`updated_at`; most business
entities also have `created_by`/`updated_by` and a soft-delete flag
(`is_active` / `deleted_at`) rather than hard deletes, per the brief's
explicit requirement (section 34).

## Core tables

| Table | Purpose |
|---|---|
| `departments`, `users`, `refresh_sessions`, `login_history` | Identity & session management |
| `materials`, `material_categories` | Material master (flexible, not hardcoded) |
| `inventory_transactions` | **Immutable ledger** - every stock change, ever. `materials.current_stock` is a derived cache updated only inside `apply_stock_transaction()` |
| `material_requests`, `material_request_items`, `request_approvals` | The request → approval → fulfillment workflow |
| `suppliers`, `purchase_orders`, `purchase_order_items`, `goods_receipts` | Purchasing |
| `production_jobs`, `production_job_materials`, `dispatch_orders` | Planning & Dispatch |
| `budgets`, `expenses` | Accounts |
| `costing_rate_master`, `cost_estimates` | The Ready Reckoner rate table + saved estimates |
| `notifications`, `audit_logs` | In-app notifications; immutable audit trail |
| `devices`, `system_settings` | License/device activation registry |

## Why an immutable ledger instead of just a `current_stock` column

This is the single most important design decision for data integrity. A
naive design lets any client PUT a new stock number directly (this is
exactly what the original ZIP did). Instead:

1. Clients only ever send a **delta** (issue 500, receive 3000, etc.), never
   a resulting total.
2. `apply_stock_transaction()` (`app/services/inventory.py`) locks the
   material row (`SELECT ... FOR UPDATE`), reads the current balance,
   validates the delta won't take stock negative, writes the new balance,
   and inserts an `InventoryTransaction` row - all inside one DB
   transaction.
3. `current_stock` can always be recomputed and cross-checked as
   `SUM(inventory_transactions.quantity)` for a given material - it's a
   cache of the ledger, not a second source of truth.

This is what makes concurrent stock operations safe (see `SECURITY.md` and
`tests/test_inventory.py::test_concurrent_issues_never_corrupt_stock`).

## Enums

Defined once in `app/models/enums.py` and reused everywhere: `TxnType`,
`RequestStatus`, `PurchaseOrderStatus`, `JobStatus`, `DispatchStatus`,
`ExpenseCategory`, `DepartmentCode`. `CROSS_DEPARTMENT_ROLES = {MANAGER,
SUB_ADMIN}` is the single place that defines who can see every department's
data - see `SECURITY.md`.

## Schema migrations

The current build uses `Base.metadata.create_all()` at startup, which is
fine for a fresh install but does **not** apply changes to an existing
production database's schema. Before making a schema change against a live
office database, introduce Alembic (`pip install alembic` is already in
`requirements.txt`) and generate a migration rather than relying on
`create_all`. This wasn't wired up in this pass - see `ARCHITECTURE.md`'s
limitations section.
