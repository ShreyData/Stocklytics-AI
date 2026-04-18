# Billing Module — Completed Implementation

This document summarises all work completed on the `feature/billing-module` branch to deliver the Billing Module of the Stocklytics AI modular monolith.

---

## Overview

The Billing Module converts a basket of line items into a **fully atomic billing transaction**. Stock is validated for all items before any write occurs, deducted as part of a single Firestore transaction, and protected end-to-end by a mandatory idempotency key so that safe retries are always possible.

---

## Files Added

| File | Purpose |
|------|---------|
| `app/modules/billing/schemas.py` | Pydantic models — `TransactionCreateRequest`, `LineItemRequest`, `TransactionResponse` |
| `app/modules/billing/repository.py` | Firestore reads and the atomic `create_billing_transaction()` write |
| `app/modules/billing/service.py` | Idempotency check, stock validation, payload assembly, transaction orchestration |
| `app/modules/billing/router.py` | Single thin POST route handler |
| `tests/test_billing.py` | 19 unit tests with all Firestore I/O fully mocked |

---

## API Endpoint

| Method | Path | Status Code | Description |
|--------|------|-------------|-------------|
| `POST` | `/api/v1/billing/transactions` | 201 | Create a new billing transaction |
| `POST` | `/api/v1/billing/transactions` | 200 | Idempotent replay — same key, same payload |
| `POST` | `/api/v1/billing/transactions` | 409 | Idempotency key conflict — same key, different payload |

All requests require a valid Firebase Bearer token. Responses always include `request_id`.

---

## Request Payload

```json
{
  "idempotency_key": "order-2026-001",
  "items": [
    { "product_id": "prod_abc", "quantity": 10, "unit_price": 9.99 }
  ],
  "notes": "Optional order notes"
}
```

`idempotency_key` is **required**. `items` must contain at least one entry with `quantity >= 1`.

---

## Firestore Collections

### `transactions`
One document per completed billing transaction. Key fields: `transaction_id`, `store_id`, `idempotency_key`, `items` (array with `line_total`), `total_amount`, `status`, `notes`, `created_by`, `created_at`.

### `billing_idempotency`
One document per unique `{store_id}::{idempotency_key}` pair. Stores the `payload_hash` and a full `transaction_snapshot` for replay. Document ID format prevents cross-tenant key collisions.

### `products` *(read from Inventory)*
Read-only in this module. Queried to validate product existence, store ownership, and `quantity_on_hand` before any write.

### `stock_adjustments`
One `SALE_DEDUCTION` record written per line item, referencing the `transaction_id` as `source_ref`. Shares the same collection as the Inventory module audit trail.

---

## Execution Flow

```
POST /api/v1/billing/transactions
  │
  ├── 1. Validate request payload (Pydantic)
  │
  ├── 2. Check billing_idempotency for idempotency_key
  │       ├── Key exists + same payload hash  → return stored result (HTTP 200)
  │       └── Key exists + different hash      → raise 409 CONFLICT
  │
  ├── 3. Batch-fetch all requested products from Firestore (read-only)
  │
  ├── 4. Validate product existence and store ownership
  │       └── Any missing / wrong-store product → raise 404
  │
  ├── 5. Validate stock for ALL items
  │       └── Any item insufficient → raise 400, NO writes performed
  │
  └── 6. Open single Firestore atomic transaction:
          ├── Write  → transactions/{transaction_id}
          ├── Update → products/{id}.quantity_on_hand    (one per line item)
          ├── Write  → stock_adjustments/{adj_id}         (one per line item)
          └── Write  → billing_idempotency/{store_id}::{key}
      → HTTP 201
```

---

## Business Rules Enforced

- **Strictly atomic** — Firestore's `async with db.transaction()` wraps all four write types. Any failure triggers an automatic full rollback; partial writes are impossible by design.
- **All-or-nothing stock validation** — all products are fetched and all quantities checked *before* the Firestore transaction opens. A single item with insufficient stock rejects the entire request with `400`.
- **No write on stock failure** — `create_billing_transaction()` is never called if stock validation fails. This is verified by a dedicated mock-assertion test.
- **Mandatory idempotency** — `idempotency_key` is a required field. Callers that retry a request on network failure with the same key receive the original result safely without double-charging or double-deducting stock.
- **Payload hashing** — the idempotency record stores a SHA-256 hash of `items` (sorted by `product_id` for order-stability). A different hash on the same key raises `409 IDEMPOTENCY_KEY_CONFLICT`.
- **Tenant-scoped idempotency** — document IDs in `billing_idempotency` are `{store_id}::{idempotency_key}`, ensuring keys are fully isolated per store.
- **Audit trail** — one `SALE_DEDUCTION` record is written to `stock_adjustments` per line item, with `source_ref` set to the `transaction_id` for full traceability.
- **Module isolation** — billing reads the `products` Firestore collection directly. It does not import or call any Python code from the Inventory module, preserving clean module boundaries.

---

## Architecture Decisions

- **Pre-computation before the transaction** — all document IDs, timestamps, line totals, and hashes are computed in Python before the Firestore transaction opens. This keeps the transaction body minimal and reduces the risk of contention timeouts.
- **`db.get_all()` for batch product reads** — avoids N serial `document.get()` calls; Firestore fetches all requested product documents in a single RPC.
- **Idempotent replay short-circuits early** — on a confirmed replay, the service returns immediately from the stored `transaction_snapshot` without opening a Firestore transaction or touching any collection.
- **`line_total` computed server-side** — `quantity * unit_price` is computed and stored on the server; callers cannot pass a pre-computed total.

---

## Test Coverage

| Test Class | Scenarios Covered |
|------------|-------------------|
| `TestCreateTransactionSuccess` | 201 happy path, `request_id` in envelope, full body shape, `status=COMPLETED`, correct `total_amount`, auth guard → 401, empty `items` → 400, missing `idempotency_key` → 400, `quantity=0` → 400 |
| `TestInsufficientStock` | Single item over-request → 400, error envelope shape, `insufficient_items` in `details`, Firestore write mock never called, missing product → 404 |
| `TestIdempotency` | Replay → HTTP 200, replay returns original `transaction_id`, write not called on replay, conflicting payload → 409, 409 follows error envelope, `error.code = CONFLICT` |

**Result: 19 / 19 tests passing.**
