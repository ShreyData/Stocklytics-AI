# Alerts Module — Remaining (Dependency-Based)

The core API-facing implementation of the Alerts Module is complete (see `completed.md`).
The items below are pending and depend on other modules or scheduled infrastructure being in place.

---

## 1. Alert Engine — Condition Detection (depends on Inventory + Billing + Analytics)

The service layer exposes an `engine.py` component to run evaluations. The following rule-evaluation jobs are implemented:

| Rule | Trigger Mode | Dependency | Status |
|------|-------------|------------|--------|
| `LOW_STOCK` (real-time) | After successful billing deduction or manual stock removal | Billing Module post-hook | ~~Done~~ |
| `LOW_STOCK` (scheduled) | Hourly reconciliation sweep | Cloud Run Job / scheduler | ~~Done~~ |
| `EXPIRY_SOON` | Daily — products expiring within 7 days with stock > 0 | Inventory Module + scheduler | ~~Done~~ |
| `NOT_SELLING` | Daily — products with stock > 0 and no sales in last 14 days | Scheduled sweep | ~~Done~~ |
| `HIGH_DEMAND` | Every 15 minutes — 3-day sales rate ≥ 1.5x baseline or stock cover < 3 days | Scheduled sweep | ~~Done~~ |

Implementation notes (implemented):
- Each job builds one `condition_key` per rule and source entity.
- If no open (non-resolved) alert exists for that `condition_key`, creates a new `ACTIVE` alert.
- If an open alert already exists, updates `message`, `severity`, and `last_evaluated_at`.
- If the condition clears, calls the resolve path with `resolved_by = "system"`.

---

## 2. Billing Module Integration

- ~~Wire `LOW_STOCK` real-time trigger: after `billing.service` successfully commits a billing transaction, call the alert engine to evaluate stock levels for all sold products.~~ (Completed)
- ~~This must happen **after** the atomic Firestore transaction commits — not inside it.~~ (Completed)

---

## 3. Inventory Module Integration

- ~~Connect stock adjustment post-hooks: after a manual `REMOVE` or `SALE_DEDUCTION` adjustment, evaluate `LOW_STOCK` for the affected product.~~ (Completed)
- ~~Connect daily expiry sweep: after the daily health job runs, evaluate `EXPIRY_SOON` for all products in the store.~~ (Completed - implemented via standalone `run_alerts_sweep.py`)

---

## 4. Analytics Module Integration

- Completed by alerts-owned scheduled evaluations that read operational products + transactions data and enforce rule semantics directly.
- Current behavior does not require synchronous coupling to analytics endpoints; freshness/pipeline lag can still affect when recent sales become visible if upstream writes are delayed.

---

## 5. AI Module Integration

- Update the AI context builder (`ai/service.py`) to query `ACTIVE` and `ACKNOWLEDGED` alerts from Firestore when constructing context for a user query.
- Alerts data is already shaped to be AI-readable — the integration only requires the AI module to call `alerts.repository.list_alerts()` with `status` filter.

---

## 6. Scheduled Jobs Infrastructure

- ~~Create Cloud Run Job definitions (or Cloud Scheduler triggers) for:~~ (Completed via `run_alerts_sweep.py` script)
  - ~~Hourly `LOW_STOCK` sweep~~
  - ~~Daily `EXPIRY_SOON` sweep~~
  - ~~Daily `NOT_SELLING` sweep~~
  - ~~15-minute `HIGH_DEMAND` sweep~~
- Jobs should call internal service functions, not go through the HTTP API. (Implemented via python CLI)

---

## 7. Frontend Integration

- Frontend must call `GET /api/v1/alerts/` to display the alert list with status badges.
- Frontend must call `GET /api/v1/alerts/summary` for dashboard alert count cards.
- Frontend must support `POST /{alert_id}/acknowledge` and `POST /{alert_id}/resolve` action buttons with the correct request body shape (`store_id` required in both).
- Frontend must display `freshness_status` if alert data is derived from analytics.
