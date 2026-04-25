## Summary

Aligns the Billing Module with the approved Plan contracts and rules: atomic transaction creation, mandatory `idempotency_key`, inventory deductions with audit logging, and the approved billing request/response shapes.

## Endpoints Included

```text
POST /api/v1/billing/transactions
GET  /api/v1/billing/transactions
GET  /api/v1/billing/transactions/{transaction_id}
```

## Files Changed

| File | Change |
|------|--------|
| `app/modules/billing/schemas.py` | Updated — request/response models aligned to Plan contracts |
| `app/modules/billing/repository.py` | Updated — atomic Firestore write path and billing query helpers |
| `app/modules/billing/service.py` | Updated — store-scope validation, idempotency handling, stock validation, read endpoints |
| `app/modules/billing/router.py` | Updated — POST + GET route handlers aligned with approved API surface |
| `tests/test_billing.py` | Updated — contract and failure-path coverage for create/replay/read flows |
| `docs/feature/billing-module/completed.md` | Updated — implementation notes aligned to final billing contract |

## Key Changes

- `store_id`, `customer_id`, and `payment_method` now follow the approved billing request contract
- Billing line-item prices are derived from inventory product data instead of client-supplied `unit_price`
- New transaction responses include `idempotent_replay` and `inventory_updates` per approved API contract
- Idempotency records now use approved billing fields: `request_hash`, `result_status`, `response_snapshot`, and `last_seen_at`
- Transaction records now include `customer_id`, `payment_method`, and `sale_timestamp`
- Added `GET /transactions` and `GET /transactions/{transaction_id}` with store-scoped reads
- Atomic Firestore billing commit revalidates stock inside the transaction to avoid stale pre-check races
- Duplicate line items are aggregated for stock validation before commit

## Architecture

- Routes stay thin; billing orchestration remains centralized in `service.py`
- Firestore access remains isolated in `repository.py`
- Billing still commits transaction record, inventory deductions, stock-adjustment audit rows, and idempotency record in one atomic path

## Tests

Billing tests now cover create success, replay, conflict, insufficient stock, missing product, pagination, and fetch-one transaction scenarios.
