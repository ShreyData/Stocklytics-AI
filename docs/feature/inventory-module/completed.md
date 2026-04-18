# Inventory Module — Completed Implementation

This document summarises all work completed on the `feature/inventory-module` branch to deliver the Inventory Module of the Stocklytics AI modular monolith.

---

## Overview

The Inventory Module is the **single source of truth for product stock levels** across the system. It manages the full lifecycle of products — creation, retrieval, updates, and stock changes — while enforcing strict business rules around stock integrity and expiry tracking.

---

## Files Added

| File | Purpose |
|------|---------|
| `app/modules/inventory/schemas.py` | Pydantic request/response models for products and stock adjustments |
| `app/modules/inventory/repository.py` | All Firestore reads/writes for `products` and `stock_adjustments` collections |
| `app/modules/inventory/service.py` | Business logic — expiry computation, negative-stock guard, adjustment orchestration |
| `app/modules/inventory/router.py` | Thin FastAPI route handlers delegating to the service layer |
| `tests/test_inventory.py` | 19 unit tests with all Firestore I/O fully mocked |

---

## API Endpoints

| Method | Path | Status Code | Description |
|--------|------|-------------|-------------|
| `POST` | `/api/v1/inventory/products` | 201 | Create a new product |
| `GET` | `/api/v1/inventory/products` | 200 | List products with optional filters |
| `GET` | `/api/v1/inventory/products/{product_id}` | 200 / 404 | Get a single product |
| `PATCH` | `/api/v1/inventory/products/{product_id}` | 200 | Partially update a product |
| `POST` | `/api/v1/inventory/products/{product_id}/stock-adjustments` | 201 | Record a stock change |

All endpoints require a valid Firebase Bearer token. Responses always include `request_id`.

---

## Firestore Collections

### `products`
Stores the product master record. Key fields: `product_id`, `store_id`, `name`, `category`, `price`, `quantity_on_hand`, `reorder_threshold`, `expiry_date`, `expiry_status`, `status`, `created_at`, `updated_at`.

### `stock_adjustments`
Append-only audit log. Every stock change appends one record. Key fields: `adjustment_id`, `store_id`, `product_id`, `adjustment_type`, `quantity_delta`, `reason`, `source_ref`, `created_by`, `created_at`.

---

## Business Rules Enforced

- **Stock never goes negative** — `apply_stock_adjustment()` computes the resulting quantity and raises `400 INVALID_REQUEST` before any Firestore write if it would go below zero.
- **Expiry status is always computed** — `compute_expiry_status()` in `service.py` derives `EXPIRED`, `EXPIRING_SOON` (within 7 days), or `OK` from the UTC clock on every create and update. Callers cannot override it.
- **Store scoping** — every product query is filtered by `store_id` extracted from the Firebase Auth token. A product belonging to a different store returns `404` to prevent cross-tenant data leakage.
- **Immutable audit trail** — every stock adjustment writes a record to `stock_adjustments`. The collection is append-only; records are never modified or deleted.
- **Partial updates** — `PATCH` uses Pydantic `model_fields_set` to update only the exact fields the caller explicitly sent. Unset fields are not touched.
- **Adjustment types** — four supported types: `ADD`, `REMOVE`, `SALE_DEDUCTION`, `MANUAL_CORRECTION`. `REMOVE` and `SALE_DEDUCTION` decrease stock; `ADD` and `MANUAL_CORRECTION` increase it.

---

## Architecture Decisions

- **Thin routes, fat service** — route handlers only parse HTTP input and return responses. All domain decisions live in `service.py`.
- **Repository isolation** — `repository.py` is the sole Firestore accessor. The service layer never builds queries or references collection names directly.
- **Async Firestore client** — uses `google.cloud.firestore.AsyncClient` for non-blocking I/O compatible with FastAPI's async event loop.
- **Client-side `low_stock_only` filter** — Firestore cannot natively express `quantity_on_hand <= reorder_threshold` in a compound query without a custom composite index. Filtering is applied after the query to avoid index management overhead.

---

## Query Filters (GET /products)

| Parameter | Type | Behaviour |
|-----------|------|-----------|
| `low_stock_only` | `bool` (default: `false`) | Returns only products where `quantity_on_hand <= reorder_threshold` |
| `expiry_before` | ISO-8601 datetime (optional) | Returns only products whose `expiry_date` is before the given value |

---

## Test Coverage

| Test Class | Scenarios Covered |
|------------|-------------------|
| `TestCreateProduct` | 201 happy path, `request_id` in response, required field validation, negative quantity → 400, auth guard → 401, `expiry_status=OK` for no-expiry products |
| `TestNegativeStockPrevention` | `REMOVE` exceeding stock → 400, `SALE_DEDUCTION` exceeding stock → 400, exact depletion to 0 succeeds, `ADD` always succeeds, non-existent product → 404, invalid `adjustment_type` → 400 |
| `TestUpdateProduct` | 200 with updated fields, `request_id` present, name updated correctly, ghost product → 404, auth guard → 401, invalid `status` → 400, deactivation succeeds |

**Result: 19 / 19 tests passing.**
