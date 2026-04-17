# RetailMind AI Naming And Conventions

## 1. Purpose
- Keep naming consistent across backend, frontend, database, APIs, and docs.
- Reduce confusion when multiple developers work in parallel.

## 2. Core Naming Rules

### API Paths
- Use lowercase and kebab-case.
- Examples:
  - `/api/v1/inventory/products`
  - `/api/v1/analytics/sales-trends`
  - `/api/v1/alerts/summary`

### JSON Fields
- Use `snake_case` for request and response fields.
- Examples:
  - `store_id`
  - `product_id`
  - `analytics_last_updated_at`
  - `idempotency_key`

### Firestore Collections
- Use plural `snake_case`.
- Examples:
  - `products`
  - `transactions`
  - `customers`
  - `alerts`
  - `pipeline_runs`
  - `pipeline_failures`

### Firestore Document IDs
- Use readable prefixed IDs when app-generated.
- Examples:
  - `store_001`
  - `prod_rice_5kg`
  - `txn_001`
  - `alert_001`
  - `pipe_run_001`

### BigQuery Datasets And Tables
- Use lowercase `snake_case`.
- Examples:
  - `retailmind_raw.transactions_raw`
  - `retailmind_mart.sales_daily`
  - `retailmind_mart.product_sales_daily`

### Python Code
- Files: `snake_case`
- Functions: `snake_case`
- Variables: `snake_case`
- Classes: `PascalCase`
- Constants and enums: `UPPER_SNAKE_CASE`

### Frontend Code
- UI components: `PascalCase`
- Hooks and helpers: `camelCase` if the frontend framework expects it
- API payload fields must still stay `snake_case`

## 3. Shared Field Names
- Always use these names exactly:
  - `store_id`
  - `product_id`
  - `transaction_id`
  - `customer_id`
  - `alert_id`
  - `chat_session_id`
  - `pipeline_run_id`
  - `idempotency_key`
  - `request_id`
  - `analytics_last_updated_at`
  - `freshness_status`

## 4. Status And Enum Rules
- Status values should be uppercase when they are workflow states.
- Examples:
  - `ACTIVE`
  - `ACKNOWLEDGED`
  - `RESOLVED`
  - `COMPLETED`
  - `FAILED`
- Small label-style values can stay lowercase when already defined in the API.
- Examples:
  - `fresh`
  - `delayed`
  - `stale`
  - `cash`
  - `upi`

## 5. Time, Currency, And Number Rules
- Store timestamps in ISO 8601 UTC format in APIs.
- Example:
  - `2026-04-02T10:45:00Z`
- Use Firestore timestamps in storage, but serialize to ISO 8601 in API responses.
- Currency values should be numeric and treated as INR in MVP.
- Quantities should be integers unless a module explicitly needs decimal quantities later.

## 6. Response Naming Rules
- Success responses should use clear top-level names:
  - `product`
  - `transaction`
  - `customer`
  - `summary`
  - `items`
  - `points`
  - `alert`
- Error responses should always use:
  - `request_id`
  - `error.code`
  - `error.message`
  - `error.details`

## 7. Folder And Module Naming
- Use the approved module names in docs and discussions:
  - Inventory Module
  - Billing Module
  - Customer Module
  - Analytics Module
  - Alerts Module
  - AI Module
  - Data Pipeline Module
  - API Module
  - Frontend Module
- Keep backend folder names in lowercase snake_case:
  - `inventory`
  - `billing`
  - `customer`
  - `analytics`
  - `alerts`
  - `ai`
  - `data_pipeline`

## 8. Logging Key Names
- Use the same key names in logs and trace context:
  - `request_id`
  - `store_id`
  - `transaction_id`
  - `product_id`
  - `customer_id`
  - `alert_id`
  - `pipeline_run_id`
  - `idempotency_key`

## 9. Practical Rules
- Do not create alternate field names for the same thing.
- Do not mix `camelCase` and `snake_case` in API payloads.
- Do not rename collection names without team agreement.
- If a field name changes, update docs before code merge.
