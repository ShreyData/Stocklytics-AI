## Summary

Implements the Billing Module — converts a basket of line items into a fully atomic billing transaction with mandatory idempotency, all-or-nothing stock validation, and a complete audit trail, all committed inside a single Firestore transaction.

## Endpoint Added

```
POST /api/v1/billing/transactions
```

| Scenario | Status |
|----------|--------|
| New transaction — all stock available | 201 |
| Idempotent replay — same key, same payload | 200 |
| Conflicting replay — same key, different payload | 409 |
| Insufficient stock | 400 |
| Missing product | 404 |

## Files Changed

| File | Change |
|------|--------|
| `app/modules/billing/schemas.py` | Added — Pydantic request/response models |
| `app/modules/billing/repository.py` | Added — Firestore reads + atomic write |
| `app/modules/billing/service.py` | Added — idempotency, stock validation, orchestration |
| `app/modules/billing/router.py` | Replaced stub — single POST route handler |
| `tests/test_billing.py` | Added — 19 unit tests |

## Key Changes

- **Atomic Firestore transaction** — a single `async with db.transaction()` block writes the transaction record, decrements stock on every product, inserts a `SALE_DEDUCTION` audit row per line item, and saves the idempotency record. Any failure rolls back everything
- **All-or-nothing stock validation** — all quantities are checked *before* the transaction opens; a single short item rejects the whole request with `400` and zero writes are performed
- **Mandatory idempotency** — `idempotency_key` is required. Same key + same payload returns the original result safely (HTTP 200). Same key + different payload returns `409 IDEMPOTENCY_KEY_CONFLICT`
- **Payload hashing** — idempotency record stores a SHA-256 hash of `items` (sorted by `product_id`) to detect conflicting replays reliably
- **Tenant-scoped idempotency keys** — document IDs in `billing_idempotency` are `{store_id}::{key}` to prevent cross-store collisions
- **Module isolation** — reads the `products` collection directly; does not import any Inventory module Python code

## Architecture

- All business logic in `service.py`; route handler is a single delegation call
- Products batch-fetched with `db.get_all()` (one RPC, not N serial calls)
- All document IDs and timestamps computed before the Firestore transaction opens, minimising transaction duration

## Tests

19 / 19 passing — covers success path, insufficient stock (with mock assertion that no write is called), idempotent replay, and idempotency conflict.

## Related Docs

`docs/feature/billing-module/completed.md`
