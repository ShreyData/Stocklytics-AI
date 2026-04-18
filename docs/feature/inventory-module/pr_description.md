## Summary

Implements the complete Inventory Module for Stocklytics AI — product management, stock level tracking, expiry status computation, and an immutable stock adjustment audit trail.

## Endpoints Added

```
POST   /api/v1/inventory/products
GET    /api/v1/inventory/products
GET    /api/v1/inventory/products/{product_id}
PATCH  /api/v1/inventory/products/{product_id}
POST   /api/v1/inventory/products/{product_id}/stock-adjustments
```

## Files Changed

| File | Change |
|------|--------|
| `app/modules/inventory/schemas.py` | Added — Pydantic request/response models |
| `app/modules/inventory/repository.py` | Added — Firestore I/O layer |
| `app/modules/inventory/service.py` | Added — business logic layer |
| `app/modules/inventory/router.py` | Replaced stub — full route handlers |
| `tests/test_inventory.py` | Added — 19 unit tests |

## Key Changes

- **Negative stock guard** — stock adjustments that would result in quantity < 0 are rejected with `400` before any Firestore write
- **Expiry status auto-computed** — `EXPIRED` / `EXPIRING_SOON` (≤7 days) / `OK` derived from UTC clock on every create and update; cannot be set by callers
- **Store scoping** — all queries filtered by `store_id` from the auth token; wrong store returns `404`
- **Immutable audit trail** — every stock change appends a `SALE_DEDUCTION` / `REMOVE` / `ADD` record to `stock_adjustments`
- **Partial PATCH** — only fields explicitly provided by the caller are updated

## Architecture

- Routes are thin; all domain logic lives in `service.py`
- `repository.py` is the sole Firestore accessor — service never builds queries directly
- Async Firestore client used throughout for FastAPI compatibility

## Tests

19 / 19 passing — covers happy paths, auth guards, negative stock prevention, partial updates, and 404 handling.

## Related Docs

`docs/feature/inventory-module/completed.md`
