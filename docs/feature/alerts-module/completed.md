# Alerts Module — Completed Implementation

This document summarises all work completed on the `feature/alerts-module` branch to deliver the Alerts Module of the RetailMind AI modular monolith.

---

## Overview

The Alerts Module detects and surfaces urgent store conditions for `LOW_STOCK` and `EXPIRY_SOON` in this phase. It manages the full alert lifecycle — from detection through acknowledgement to resolution — and makes alert data available to both the frontend UI and the AI assistant.

---

## Files Added

| File | Purpose |
|------|---------|
| `app/modules/alerts/schemas.py` | Pydantic request/response models, lifecycle status constants, allowed transition map |
| `app/modules/alerts/repository.py` | All Firestore reads/writes for `alerts` collection and `alerts/{alert_id}/events` subcollection, plus `get_alert_by_condition` |
| `app/modules/alerts/service.py` | Business logic — list, summary, acknowledge, resolve, lifecycle validation, event writing |
| `app/modules/alerts/engine.py` | Business logic — core rule evaluation for `LOW_STOCK` and `EXPIRY_SOON`, orchestrates lifecycle state transitions |
| `app/modules/alerts/router.py` | Thin FastAPI route handlers delegating to the service layer (replaced stub) |
| `app/modules/billing/service.py` | Added post-transaction hook to fire `LOW_STOCK` evaluation asynchronously |
| `app/modules/inventory/service.py` | Added post-adjustment hook to fire `LOW_STOCK` evaluation asynchronously |
| `scripts/run_alerts_sweep.py` | CLI script for Cloud Run Jobs to trigger hourly (`LOW_STOCK`) and daily (`EXPIRY_SOON`) evaluation sweeps |
| `tests/test_alerts.py` | 28 unit tests with all Firestore I/O fully mocked |
| `tests/test_alerts_engine.py` | Unit tests for engine evaluation logic |

---

## API Endpoints

| Method | Path | Status Code | Description |
|--------|------|-------------|-------------|
| `GET` | `/api/v1/alerts/` | 200 | List alerts with optional filters |
| `GET` | `/api/v1/alerts/summary` | 200 | Alert counts for dashboard cards |
| `POST` | `/api/v1/alerts/{alert_id}/acknowledge` | 200 | Move `ACTIVE` → `ACKNOWLEDGED` |
| `POST` | `/api/v1/alerts/{alert_id}/resolve` | 200 | Move `ACTIVE` or `ACKNOWLEDGED` → `RESOLVED` |

All endpoints require a valid Firebase Bearer token. Responses always include `request_id`.

---

## Query Filters (GET /alerts/)

| Parameter | Type | Allowed Values | Default |
|-----------|------|----------------|---------|
| `status` | string | `ACTIVE`, `ACKNOWLEDGED`, `RESOLVED` | none |
| `alert_type` | string | `LOW_STOCK`, `EXPIRY_SOON`, `NOT_SELLING`, `HIGH_DEMAND` | none |
| `severity` | string | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` | none |
| `store_id` | string | Must match authenticated store scope | none |

Invalid enum values return `400 INVALID_QUERY`.

---

## Firestore Collections

### `alerts`
Stores one document per alert. Key fields: `alert_id`, `store_id`, `alert_type`, `condition_key`, `source_entity_id`, `status`, `severity`, `title`, `message`, `metadata`, `created_at`, `acknowledged_at`, `acknowledged_by`, `resolved_at`, `resolved_by`, `resolution_note`, `last_evaluated_at`.

### `alerts/{alert_id}/events`
Append-only lifecycle audit log. Every status transition writes one event record. Key fields: `event_id`, `from_status`, `to_status`, `changed_by`, `note`, `changed_at`.

---

## Alert Lifecycle Enforced

```
[*] --> ACTIVE
ACTIVE --> ACKNOWLEDGED   (user acknowledges)
ACTIVE --> RESOLVED       (direct resolution allowed)
ACKNOWLEDGED --> RESOLVED (user or system resolves)
```

- `RESOLVED` is a terminal state — no further transitions are permitted.
- Attempting any transition out of `RESOLVED` returns `409 INVALID_ALERT_TRANSITION`.
- Attempting to acknowledge an `ACKNOWLEDGED` or `RESOLVED` alert returns `409 INVALID_ALERT_TRANSITION`.
- Only `ACTIVE` alerts can be acknowledged.

---

## Business Rules Enforced

- **Lifecycle validation** — `_validate_transition()` in `service.py` enforces `ALLOWED_TRANSITIONS` map and raises `409 INVALID_ALERT_TRANSITION` on invalid moves.
- **Event logging** — every status transition calls `repository.write_alert_event()`, writing an immutable record to `alerts/{alert_id}/events`.
- **Store scoping** — `store_id` in request body and query params is always validated against the authenticated token scope.
- **Timestamps stamped at transition** — `acknowledged_at` / `resolved_at` are set in the service at the moment the action is processed, never client-supplied.
- **Actor recorded** — `acknowledged_by` and `resolved_by` are set from the authenticated `user.user_id`, not from the request body.
- **Resolved alerts remain queryable** — resolved records are never deleted, supporting history and AI context queries.
- **`resolved_today` counter** — summary counts alerts whose `resolved_at` falls on the current UTC calendar day.

---

## Architecture Decisions

- **Thin routes, fat service** — route handlers only parse HTTP input and return responses. All lifecycle decisions live in `service.py`.
- **Repository isolation** — `repository.py` is the sole Firestore accessor. The service layer never touches collection names or builds queries directly.
- **Async Firestore client** — uses `google.cloud.firestore.AsyncClient` for non-blocking I/O compatible with FastAPI's async event loop.
- **Constants in `schemas.py`** — `ALLOWED_TRANSITIONS`, `VALID_ALERT_STATUSES`, `VALID_ALERT_TYPES`, and `VALID_ALERT_SEVERITIES` are all defined once and imported by both router and service to avoid magic strings.

---

## Error Cases Covered

| Scenario | HTTP | Code |
|----------|------|------|
| Alert not found or wrong store | `404` | `ALERT_NOT_FOUND` |
| Invalid lifecycle transition | `409` | `INVALID_ALERT_TRANSITION` |
| Invalid query param enum value | `400` | `INVALID_QUERY` |
| `store_id` mismatch | `400` | `INVALID_REQUEST` |
| Missing Bearer token | `401` | `UNAUTHORIZED` |

---

## Test Coverage

**Result: 29 tests defined**

| Test Class | Scenarios Covered |
|------------|-------------------|
| `TestListAlerts` | 200 list, `request_id`, `items` key, empty store, 401 guard, bad `status`/`alert_type`/`severity` → 400, valid filter accepted |
| `TestAlertSummary` | 200 summary, required fields present, `active` count, `acknowledged` count, 401 guard |
| `TestAcknowledgeAlert` | 200 acknowledge ACTIVE, `status=ACKNOWLEDGED` in response, 409 on ACKNOWLEDGED→ACKNOWLEDGED, 409 on RESOLVED→ACKNOWLEDGED, 404 unknown alert, 401 guard, `request_id` in envelope |
| `TestResolveAlert` | 200 from ACTIVE, 200 from ACKNOWLEDGED, `status=RESOLVED` in response, 409 on RESOLVED→RESOLVED, 404 unknown alert, 401 guard, `resolution_note` in response |
