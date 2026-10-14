# API Reference

Interactive OpenAPI docs are available at `/api/docs` when
`DEBUG=true` (development only - disabled in production).

All endpoints require `Authorization: Bearer <access_token>` except
`/api/auth/login`, `/api/auth/refresh`, and `/api/health`.
Department access is noted per group; **MANAGER and SUB_ADMIN can always
access every endpoint** in addition to what's listed.

## Auth
| Method | Path | Access |
|---|---|---|
| POST | `/api/auth/login` | Public |
| POST | `/api/auth/refresh` | Public (valid refresh token) |
| POST | `/api/auth/logout` | Authenticated |
| GET | `/api/auth/me` | Authenticated |
| POST | `/api/auth/change-password` | Authenticated |

## Materials & Inventory
| Method | Path | Access |
|---|---|---|
| GET | `/api/materials` | Any authenticated department (shared catalog) |
| GET | `/api/materials/{id}` | Any authenticated department |
| POST | `/api/materials` | STORE |
| PUT | `/api/materials/{id}` | STORE |
| GET | `/api/inventory/transactions` | STORE |
| POST | `/api/inventory/receive` | STORE |
| POST | `/api/inventory/issue` | STORE |
| POST | `/api/inventory/adjust?is_increase=bool` | STORE |
| POST | `/api/inventory/return` | STORE |

All inventory-mutating endpoints accept an optional `idempotency_key` to
make client retries safe, and reject requests that would take stock
negative with `400 Insufficient stock for <material>...`.

## Material Requests
| Method | Path | Access |
|---|---|---|
| GET / POST | `/api/material-requests` | Any (own department's requests; STORE sees all) |
| GET | `/api/material-requests/{id}` | Requesting department, STORE, or Manager/Sub-Admin |
| POST | `/api/material-requests/{id}/approve` | STORE |
| POST | `/api/material-requests/{id}/fulfill` | STORE |
| POST | `/api/material-requests/{id}/cancel` | Requesting department |

## Purchasing
| Method | Path | Access |
|---|---|---|
| GET / POST | `/api/suppliers` | STORE, ACCOUNTS |
| GET / POST | `/api/purchase-orders` | STORE, ACCOUNTS |
| POST | `/api/purchase-orders/{id}/receive` | STORE, ACCOUNTS |

## Production & Dispatch
| Method | Path | Access |
|---|---|---|
| GET / POST | `/api/production/jobs` | PLANNING |
| GET | `/api/production/jobs/{id}/availability` | PLANNING |
| PUT | `/api/production/jobs/{id}/status` | PLANNING |
| GET / POST | `/api/dispatch` | DISPATCH |
| PUT | `/api/dispatch/{id}/status` | DISPATCH |

## Accounts
| Method | Path | Access |
|---|---|---|
| GET / POST | `/api/accounts/budgets` | ACCOUNTS |
| GET / POST | `/api/accounts/expenses` | ACCOUNTS |

## Costing
| Method | Path | Access |
|---|---|---|
| GET | `/api/costing/rates` | PLANNING, ACCOUNTS |
| PUT | `/api/costing/rates` | Manager/Sub-Admin only |
| POST | `/api/costing/estimate` | PLANNING, ACCOUNTS |
| POST | `/api/costing/estimate/save` | PLANNING, ACCOUNTS |

## Reports (`?fmt=json|csv|xlsx`)
| Method | Path | Access |
|---|---|---|
| GET | `/api/reports/inventory` | STORE |
| GET | `/api/reports/low-stock` | STORE |
| GET | `/api/reports/consumption` | STORE |
| GET | `/api/reports/expenses` | ACCOUNTS |
| GET | `/api/reports/department-spending` | ACCOUNTS |

## Forecasting
| Method | Path | Access |
|---|---|---|
| GET | `/api/forecast/materials/{id}?lead_time_days=14&lookback_months=6` | STORE, PLANNING |

Returns `{"forecast_available": false, "message": "Insufficient historical data for reliable forecast."}` when fewer than 3 months of ISSUE history exist for that material.

## Users, Audit, Notifications, License
| Method | Path | Access |
|---|---|---|
| GET / POST / PUT | `/api/users` | Manager/Sub-Admin |
| DELETE | `/api/users/{id}` | Manager only |
| GET | `/api/audit-logs` | Manager only |
| GET | `/api/notifications` | Own notifications only |
| GET | `/api/license/status` | Manager/Sub-Admin |
| POST | `/api/license/activate-this-device` | Manager/Sub-Admin |
| GET | `/api/license/devices` | Manager/Sub-Admin |
| POST | `/api/license/devices/{id}/revoke` | Manager only |

## Real-time
`GET /ws?token=<access_token>` - WebSocket. Sends JSON messages
`{"event": "<EVENT_TYPE>", "data": {...}}` for `STOCK_UPDATED`, `LOW_STOCK`,
`MATERIAL_REQUEST_CREATED`, `REQUEST_APPROVED`, `REQUEST_REJECTED`,
`PURCHASE_RECEIVED`, `JOB_CREATED`, `JOB_UPDATED`, `DISPATCH_CREATED`,
`BUDGET_ALERT` - each filtered to the departments authorized to see it.
