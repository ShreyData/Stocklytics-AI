# Alerts Module — Remaining (Dependency-Based)

The core API-facing implementation of the Alerts Module is complete (see `completed.md`).
The items below are pending and depend on other modules or scheduled infrastructure being in place.

---

## 1. Alert Engine — Condition Detection (depends on Inventory + Billing + Analytics)

The service layer exposes `repository.create_alert()` and `repository.update_alert()` but no automatic trigger currently calls them. The following rule-evaluation jobs need to be built:

| Rule | Trigger Mode | Dependency |
|------|-------------|------------|
| `LOW_STOCK` (real-time) | After successful billing deduction or manual stock removal | Billing Module post-hook |
| `LOW_STOCK` (scheduled) | Hourly reconciliation sweep | Cloud Run Job / scheduler |
| `EXPIRY_SOON` | Daily — products expiring within 7 days with stock > 0 | Inventory Module + scheduler |
| `NOT_SELLING` | Daily — products with stock > 0 and no sales in last 14 days | Analytics Module refresh |
| `HIGH_DEMAND` | Every 15 minutes — 3-day sales rate ≥ 1.5x baseline or stock cover < 3 days | Analytics Module refresh |

Implementation notes:
- Each job must build one `condition_key` per rule and source entity.
- If no open (non-resolved) alert exists for that `condition_key`, create a new `ACTIVE` alert.
- If an open alert already exists, update `message`, `severity`, and `last_evaluated_at`.
- If the condition clears, call the resolve path with `resolved_by = "system"`.

---

## 2. Billing Module Integration

- Wire `LOW_STOCK` real-time trigger: after `billing.service` successfully commits a billing transaction, call the alert engine to evaluate stock levels for all sold products.
- This must happen **after** the atomic Firestore transaction commits — not inside it.

---

## 3. Inventory Module Integration

- Connect stock adjustment post-hooks: after a manual `REMOVE` or `SALE_DEDUCTION` adjustment, evaluate `LOW_STOCK` for the affected product.
- Connect daily expiry sweep: after the daily health job runs, evaluate `EXPIRY_SOON` for all products in the store.

---

## 4. Analytics Module Integration

- Connect `NOT_SELLING` detection: after each analytics pipeline refresh, query products with no recent sales from BigQuery mart and create/update alerts.
- Connect `HIGH_DEMAND` detection: every 15 minutes after analytics refresh, query products where 3-day sales rate ≥ 1.5x baseline or stock cover < 3 days.

---

## 5. AI Module Integration

- Update the AI context builder (`ai/service.py`) to query `ACTIVE` and `ACKNOWLEDGED` alerts from Firestore when constructing context for a user query.
- Alerts data is already shaped to be AI-readable — the integration only requires the AI module to call `alerts.repository.list_alerts()` with `status` filter.

---

## 6. Scheduled Jobs Infrastructure

- Create Cloud Run Job definitions (or Cloud Scheduler triggers) for:
  - Hourly `LOW_STOCK` sweep
  - Daily `EXPIRY_SOON` sweep
  - Daily `NOT_SELLING` sweep
  - 15-minute `HIGH_DEMAND` sweep
- Jobs should call internal service functions, not go through the HTTP API.

---

## 7. Frontend Integration

- Frontend must call `GET /api/v1/alerts/` to display the alert list with status badges.
- Frontend must call `GET /api/v1/alerts/summary` for dashboard alert count cards.
- Frontend must support `POST /{alert_id}/acknowledge` and `POST /{alert_id}/resolve` action buttons with the correct request body shape (`store_id` required in both).
- Frontend must display `freshness_status` if alert data is derived from analytics.
