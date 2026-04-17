# RetailMind AI Shared Business Rules

## 1. Purpose
- Define the business rules that every module must follow.
- Keep behavior consistent across API, backend, pipeline, frontend, and AI.

## 2. Store Scope Rule
- Every major record must include `store_id`.
- Every protected API request must be scoped to one store.
- No module should mix data from different stores in one response unless explicitly designed later.

## 3. Atomic Billing Rule
- Billing must be strictly all-or-nothing.
- If any product in a billing request has insufficient stock, the full transaction fails.
- No partial stock deduction is allowed.
- Transaction record, stock updates, stock adjustment logs, and idempotency record should be committed in one Firestore transaction.

## 4. Billing Idempotency Rule
- Billing create requests must include `idempotency_key`.
- Same `idempotency_key` plus same payload:
  - return the original result
  - do not create a duplicate transaction
- Same `idempotency_key` plus different payload:
  - return conflict
- Frontend should reuse the same `idempotency_key` when retrying the same billing request.

## 5. Inventory Rule
- Inventory is the live source of truth for current stock.
- Stock must never go negative.
- Manual stock adjustments must be logged.
- Expiry status should reflect the latest product expiry data.

## 6. Customer Rule
- Customer linking in billing is optional.
- Customer summary fields should update only from completed transactions.
- Purchase history should come from transactions, not duplicated arrays in customer records.

## 7. Alert Lifecycle Rule
- Alerts use these lifecycle states only:
  - `ACTIVE`
  - `ACKNOWLEDGED`
  - `RESOLVED`
- Only one non-resolved alert should exist for the same `condition_key`.
- Resolved alerts must stay available for history.
- Status changes should record timestamps and actor information when applicable.

## 8. Analytics Freshness Rule
- Analytics is not real-time in MVP.
- Analytics responses must include:
  - `analytics_last_updated_at`
  - `freshness_status`
- `analytics_last_updated_at` should update only after a successful mart refresh.
- Frontend must show freshness near analytics data.
- AI must consider freshness in responses.

## 9. AI Grounding Rule
- AI uses structured system data only.
- No heavy RAG.
- No vector database.
- AI context must be built from:
  - analytics summary
  - alerts
  - inventory snapshot
- AI should not invent insights that are not supported by current context.
- If analytics data is stale, AI should mention it clearly.

## 10. Data Pipeline Reliability Rule
- Pipeline jobs retry up to 3 times.
- If retries are exhausted:
  - mark the run failed
  - store failure details
  - keep the last successful checkpoint unchanged
- Recovery should reprocess the failed window safely.
- `analytics_last_updated_at` must not move forward on failed refreshes.

## 11. API Consistency Rule
- All APIs must use the shared error format.
- All APIs should return predictable JSON shapes.
- Use consistent HTTP status codes for validation, not found, conflict, auth, and server errors.
- Billing, analytics, alerts, and AI APIs must preserve the approved contract names.

## 12. Frontend Behavior Rule
- Frontend should never call Firestore or BigQuery directly in MVP.
- Frontend should surface billing failure clearly.
- Frontend should support safe billing retry.
- Frontend should show alert lifecycle actions and freshness indicators.

## 13. Simplicity Rule
- Keep the system as a modular monolith.
- Do not split into microservices for MVP.
- Do not add new major platform components unless the team agrees they are necessary.
- Prefer simple, clear implementation over overengineering.
