# Billing Module — Completed Implementation

This document summarises the billing implementation currently delivered on the `feature/billing-module` branch after Plan-alignment fixes.

## Overview

The Billing Module creates sales transactions with strict all-or-nothing stock validation, mandatory idempotency, and inventory audit logging. Transaction writes, stock deductions, stock-adjustment rows, and idempotency storage are committed through one atomic Firestore path.

## Files Added / Updated

| File | Purpose |
|------|---------|
| `app/modules/billing/schemas.py` | Billing request and response models aligned to approved API contracts |
| `app/modules/billing/repository.py` | Firestore reads, transaction-safe billing commit, idempotency helpers, and read queries |
| `app/modules/billing/service.py` | Billing orchestration, store-scope validation, idempotency replay/conflict logic, stock validation, and query responses |
| `app/modules/billing/router.py` | Thin POST/GET route handlers |
| `tests/test_billing.py` | Billing request, failure-path, replay, list, and fetch-one test coverage |

## API Endpoints

| Method | Path | Status Code | Description |
|--------|------|-------------|-------------|
| `POST` | `/api/v1/billing/transactions` | 201 | Create a new billing transaction |
| `POST` | `/api/v1/billing/transactions` | 200 | Safe idempotent replay |
| `GET` | `/api/v1/billing/transactions` | 200 | List billing transactions |
| `GET` | `/api/v1/billing/transactions/{transaction_id}` | 200 | Fetch one transaction |

All requests require a valid Firebase Bearer token. Responses always include `request_id`.

## Approved Request Payload

```json
{
  "store_id": "store_001",
  "idempotency_key": "bill_20260402_0001",
  "customer_id": "cust_001",
  "payment_method": "cash",
  "items": [
    { "product_id": "prod_rice_5kg", "quantity": 2 },
    { "product_id": "prod_biscuit_01", "quantity": 3 }
  ]
}
```

## Firestore Collections

### `transactions`
Stores billing records with `transaction_id`, `store_id`, `idempotency_key`, `customer_id`, `payment_method`, `status`, `total_amount`, `sale_timestamp`, `items`, `created_by`, and `created_at`.

### `billing_idempotency`
Stores one record per unique `store_id + idempotency_key` with `request_hash`, `transaction_id`, `result_status`, `response_snapshot`, `created_at`, and `last_seen_at`.

### `stock_adjustments`
Stores one `SALE_DEDUCTION` row per billed line item.

## Business Rules Enforced

- Billing is strictly atomic.
- No partial stock deduction is allowed.
- Same `idempotency_key` plus same payload returns a safe replay.
- Same `idempotency_key` plus different payload returns `409 IDEMPOTENCY_KEY_CONFLICT`.
- Insufficient stock returns `409 INSUFFICIENT_STOCK`.
- Product lookup is store-scoped and returns `404 PRODUCT_NOT_FOUND` when missing.
- Duplicate line items are aggregated for stock validation before commit.
- Stock is revalidated inside the Firestore transaction before product quantities are updated.

## Architecture Notes

- Billing logic stays centralized in one service path.
- Firestore document writes remain isolated in the repository layer.
- Billing reads live inventory data from the shared `products` collection and writes billing outputs to `transactions`, `stock_adjustments`, and `billing_idempotency`.

## Test Coverage

Billing tests cover:

- successful transaction creation
- auth and payload validation failures
- insufficient stock with zero writes
- missing product handling
- idempotent replay
- idempotency conflict
- list pagination
- fetch-one transaction behavior
