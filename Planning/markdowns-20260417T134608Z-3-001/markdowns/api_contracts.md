# RetailMind AI API Contracts

## 1. Shared API Rules
- Base path: `/api/v1`
- Format: JSON request and JSON response
- Auth: Firebase Auth bearer token on protected routes
- Store scope: every business request carries `store_id`
- Request tracing: server returns `request_id` in every response
- Billing write rule: billing is atomic and idempotent

## 2. Shared Error Model
```json
{
  "request_id": "req_01HZZ1XG1Y2",
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "One or more products do not have enough stock.",
    "details": {
      "failed_items": [
        {
          "product_id": "prod_rice_5kg",
          "requested_quantity": 4,
          "available_quantity": 2
        }
      ]
    }
  }
}
```

## 3. Inventory APIs

### POST /api/v1/inventory/products
- Purpose: add a product to inventory

Request:
```json
{
  "store_id": "store_001",
  "name": "Rice 5kg",
  "price": 320.0,
  "quantity": 25,
  "expiry_date": "2026-06-30T00:00:00Z",
  "reorder_threshold": 8,
  "category": "Grocery"
}
```

Response `201`:
```json
{
  "request_id": "req_inv_001",
  "product": {
    "product_id": "prod_rice_5kg",
    "store_id": "store_001",
    "name": "Rice 5kg",
    "price": 320.0,
    "quantity_on_hand": 25,
    "expiry_date": "2026-06-30T00:00:00Z",
    "reorder_threshold": 8,
    "expiry_status": "OK",
    "created_at": "2026-04-02T10:00:00Z"
  }
}
```

Error cases:
- `400 INVALID_REQUEST`
- `409 PRODUCT_ALREADY_EXISTS`

### GET /api/v1/inventory/products
- Purpose: list products with stock and expiry status
- Query params: `store_id`, `limit`, `page_token`, `low_stock_only`, `expiry_before`

Response `200`:
```json
{
  "request_id": "req_inv_002",
  "items": [
    {
      "product_id": "prod_rice_5kg",
      "name": "Rice 5kg",
      "price": 320.0,
      "quantity_on_hand": 25,
      "expiry_date": "2026-06-30T00:00:00Z",
      "expiry_status": "OK"
    }
  ],
  "next_page_token": null
}
```

Error cases:
- `400 INVALID_QUERY`
- `401 UNAUTHORIZED`

### GET /api/v1/inventory/products/{product_id}
- Purpose: fetch one product

Response `200`:
```json
{
  "request_id": "req_inv_003",
  "product": {
    "product_id": "prod_rice_5kg",
    "store_id": "store_001",
    "name": "Rice 5kg",
    "price": 320.0,
    "quantity_on_hand": 25,
    "expiry_date": "2026-06-30T00:00:00Z",
    "expiry_status": "OK",
    "updated_at": "2026-04-02T10:05:00Z"
  }
}
```

Error cases:
- `404 PRODUCT_NOT_FOUND`

### PATCH /api/v1/inventory/products/{product_id}
- Purpose: update product details

Request:
```json
{
  "store_id": "store_001",
  "price": 330.0,
  "reorder_threshold": 10,
  "expiry_date": "2026-07-15T00:00:00Z"
}
```

Response `200`:
```json
{
  "request_id": "req_inv_004",
  "product": {
    "product_id": "prod_rice_5kg",
    "price": 330.0,
    "reorder_threshold": 10,
    "expiry_date": "2026-07-15T00:00:00Z",
    "updated_at": "2026-04-02T10:10:00Z"
  }
}
```

Error cases:
- `400 INVALID_REQUEST`
- `404 PRODUCT_NOT_FOUND`

### POST /api/v1/inventory/products/{product_id}/stock-adjustments
- Purpose: add or remove stock manually

Request:
```json
{
  "store_id": "store_001",
  "adjustment_type": "ADD",
  "quantity_delta": 10,
  "reason": "Supplier delivery"
}
```

Response `200`:
```json
{
  "request_id": "req_inv_005",
  "product_id": "prod_rice_5kg",
  "new_quantity_on_hand": 35,
  "adjustment_id": "adj_001",
  "updated_at": "2026-04-02T10:20:00Z"
}
```

Error cases:
- `400 INVALID_REQUEST`
- `404 PRODUCT_NOT_FOUND`
- `409 NEGATIVE_STOCK_NOT_ALLOWED`

## 4. Billing APIs

### POST /api/v1/billing/transactions
- Purpose: create a bill and deduct stock
- Billing guarantee: all-or-nothing
- Idempotency rule: request must include `idempotency_key`

Request:
```json
{
  "store_id": "store_001",
  "idempotency_key": "bill_20260402_0001",
  "customer_id": "cust_001",
  "payment_method": "cash",
  "items": [
    {
      "product_id": "prod_rice_5kg",
      "quantity": 2
    },
    {
      "product_id": "prod_biscuit_01",
      "quantity": 3
    }
  ]
}
```

Response `201`:
```json
{
  "request_id": "req_bill_001",
  "idempotent_replay": false,
  "transaction": {
    "transaction_id": "txn_001",
    "store_id": "store_001",
    "customer_id": "cust_001",
    "status": "COMPLETED",
    "payment_method": "cash",
    "total_amount": 745.0,
    "sale_timestamp": "2026-04-02T10:30:00Z",
    "items": [
      {
        "product_id": "prod_rice_5kg",
        "quantity": 2,
        "unit_price": 320.0,
        "line_total": 640.0
      },
      {
        "product_id": "prod_biscuit_01",
        "quantity": 3,
        "unit_price": 35.0,
        "line_total": 105.0
      }
    ]
  },
  "inventory_updates": [
    {
      "product_id": "prod_rice_5kg",
      "new_quantity_on_hand": 33
    },
    {
      "product_id": "prod_biscuit_01",
      "new_quantity_on_hand": 47
    }
  ]
}
```

Response `200` for safe retry with same key and same payload:
```json
{
  "request_id": "req_bill_001_retry",
  "idempotent_replay": true,
  "transaction": {
    "transaction_id": "txn_001",
    "status": "COMPLETED",
    "total_amount": 745.0
  }
}
```

Error cases:
- `400 INVALID_REQUEST`
- `409 INSUFFICIENT_STOCK`
- `409 IDEMPOTENCY_KEY_CONFLICT`
- `404 PRODUCT_NOT_FOUND`
- `401 UNAUTHORIZED`

### Billing Failure Behavior
- Validate all line items before any stock mutation.
- If one item fails stock validation, the full request fails.
- No product stock is changed on a failed billing request.
- Transaction record and stock deductions are committed in one Firestore transaction.

### GET /api/v1/billing/transactions
- Purpose: list sales transactions
- Query params: `store_id`, `from`, `to`, `customer_id`, `limit`, `page_token`

Response `200`:
```json
{
  "request_id": "req_bill_002",
  "items": [
    {
      "transaction_id": "txn_001",
      "customer_id": "cust_001",
      "total_amount": 745.0,
      "sale_timestamp": "2026-04-02T10:30:00Z",
      "status": "COMPLETED"
    }
  ],
  "next_page_token": null
}
```

Error cases:
- `400 INVALID_QUERY`

### GET /api/v1/billing/transactions/{transaction_id}
- Purpose: fetch one transaction

Response `200`:
```json
{
  "request_id": "req_bill_003",
  "transaction": {
    "transaction_id": "txn_001",
    "store_id": "store_001",
    "customer_id": "cust_001",
    "status": "COMPLETED",
    "total_amount": 745.0,
    "sale_timestamp": "2026-04-02T10:30:00Z",
    "idempotency_key": "bill_20260402_0001",
    "items": [
      {
        "product_id": "prod_rice_5kg",
        "quantity": 2,
        "unit_price": 320.0,
        "line_total": 640.0
      }
    ]
  }
}
```

Error cases:
- `404 TRANSACTION_NOT_FOUND`

## 5. Customer APIs

### POST /api/v1/customers
- Purpose: create a customer record

Request:
```json
{
  "store_id": "store_001",
  "name": "Ravi Kumar",
  "phone": "+919999999999"
}
```

Response `201`:
```json
{
  "request_id": "req_cust_001",
  "customer": {
    "customer_id": "cust_001",
    "store_id": "store_001",
    "name": "Ravi Kumar",
    "phone": "+919999999999",
    "total_spend": 0.0,
    "visit_count": 0
  }
}
```

Error cases:
- `400 INVALID_REQUEST`
- `409 CUSTOMER_ALREADY_EXISTS`

### GET /api/v1/customers
- Purpose: list customers

Response `200`:
```json
{
  "request_id": "req_cust_002",
  "items": [
    {
      "customer_id": "cust_001",
      "name": "Ravi Kumar",
      "phone": "+919999999999",
      "total_spend": 3140.0,
      "visit_count": 9,
      "last_purchase_at": "2026-04-02T10:30:00Z"
    }
  ]
}
```

Error cases:
- `400 INVALID_QUERY`

### GET /api/v1/customers/{customer_id}
- Purpose: fetch one customer profile

Response `200`:
```json
{
  "request_id": "req_cust_003",
  "customer": {
    "customer_id": "cust_001",
    "store_id": "store_001",
    "name": "Ravi Kumar",
    "phone": "+919999999999",
    "total_spend": 3140.0,
    "visit_count": 9,
    "last_purchase_at": "2026-04-02T10:30:00Z"
  }
}
```

Error cases:
- `404 CUSTOMER_NOT_FOUND`

### GET /api/v1/customers/{customer_id}/purchase-history
- Purpose: get customer-wise sales

Response `200`:
```json
{
  "request_id": "req_cust_004",
  "customer_id": "cust_001",
  "transactions": [
    {
      "transaction_id": "txn_001",
      "total_amount": 745.0,
      "sale_timestamp": "2026-04-02T10:30:00Z"
    }
  ]
}
```

Error cases:
- `404 CUSTOMER_NOT_FOUND`

## 6. Analytics APIs

### Shared Analytics Response Fields
- `analytics_last_updated_at`
- `freshness_status`: `fresh`, `delayed`, or `stale`

### GET /api/v1/analytics/dashboard
- Purpose: fetch dashboard summary

Response `200`:
```json
{
  "request_id": "req_an_001",
  "analytics_last_updated_at": "2026-04-02T10:45:00Z",
  "freshness_status": "fresh",
  "summary": {
    "today_sales": 12450.0,
    "today_transactions": 31,
    "active_alert_count": 6,
    "low_stock_count": 4,
    "top_selling_product": "Rice 5kg"
  }
}
```

Error cases:
- `503 ANALYTICS_NOT_READY`

### GET /api/v1/analytics/sales-trends
- Purpose: get daily or weekly trend data
- Query params: `store_id`, `range`, `granularity`

Response `200`:
```json
{
  "request_id": "req_an_002",
  "analytics_last_updated_at": "2026-04-02T10:45:00Z",
  "freshness_status": "fresh",
  "points": [
    {
      "label": "2026-04-01",
      "sales_amount": 11200.0,
      "transactions": 29
    },
    {
      "label": "2026-04-02",
      "sales_amount": 12450.0,
      "transactions": 31
    }
  ]
}
```

Error cases:
- `400 INVALID_QUERY`

### GET /api/v1/analytics/product-performance
- Purpose: get product-wise sales insights

Response `200`:
```json
{
  "request_id": "req_an_003",
  "analytics_last_updated_at": "2026-04-02T10:45:00Z",
  "freshness_status": "fresh",
  "items": [
    {
      "product_id": "prod_rice_5kg",
      "product_name": "Rice 5kg",
      "quantity_sold": 48,
      "revenue": 15360.0
    }
  ]
}
```

Error cases:
- `400 INVALID_QUERY`

### GET /api/v1/analytics/customer-insights
- Purpose: get top customers and buying patterns

Response `200`:
```json
{
  "request_id": "req_an_004",
  "analytics_last_updated_at": "2026-04-02T10:45:00Z",
  "freshness_status": "fresh",
  "top_customers": [
    {
      "customer_id": "cust_001",
      "name": "Ravi Kumar",
      "lifetime_spend": 3140.0,
      "visit_count": 9
    }
  ]
}
```

Error cases:
- `503 ANALYTICS_NOT_READY`

## 7. Alerts APIs

### Alert Status Model
- `ACTIVE`
- `ACKNOWLEDGED`
- `RESOLVED`

### GET /api/v1/alerts
- Purpose: list alerts
- Query params: `store_id`, `status`, `alert_type`, `severity`

Response `200`:
```json
{
  "request_id": "req_alert_001",
  "items": [
    {
      "alert_id": "alert_001",
      "alert_type": "LOW_STOCK",
      "status": "ACTIVE",
      "severity": "HIGH",
      "title": "Rice 5kg stock is low",
      "message": "Only 3 units left. Reorder soon.",
      "created_at": "2026-04-02T10:31:00Z",
      "acknowledged_at": null,
      "resolved_at": null
    }
  ]
}
```

Error cases:
- `400 INVALID_QUERY`

### GET /api/v1/alerts/summary
- Purpose: get alert counts for dashboard cards

Response `200`:
```json
{
  "request_id": "req_alert_002",
  "summary": {
    "active": 6,
    "acknowledged": 2,
    "resolved_today": 3
  }
}
```

Error cases:
- `401 UNAUTHORIZED`

### POST /api/v1/alerts/{alert_id}/acknowledge
- Purpose: move alert from `ACTIVE` to `ACKNOWLEDGED`

Request:
```json
{
  "store_id": "store_001",
  "note": "Supplier contacted"
}
```

Response `200`:
```json
{
  "request_id": "req_alert_003",
  "alert": {
    "alert_id": "alert_001",
    "status": "ACKNOWLEDGED",
    "acknowledged_at": "2026-04-02T11:00:00Z",
    "acknowledged_by": "user_001"
  }
}
```

Error cases:
- `404 ALERT_NOT_FOUND`
- `409 INVALID_ALERT_TRANSITION`

### POST /api/v1/alerts/{alert_id}/resolve
- Purpose: move alert to `RESOLVED`

Request:
```json
{
  "store_id": "store_001",
  "resolution_note": "New stock received"
}
```

Response `200`:
```json
{
  "request_id": "req_alert_004",
  "alert": {
    "alert_id": "alert_001",
    "status": "RESOLVED",
    "resolved_at": "2026-04-02T12:00:00Z",
    "resolved_by": "user_001",
    "resolution_note": "New stock received"
  }
}
```

Error cases:
- `404 ALERT_NOT_FOUND`
- `409 INVALID_ALERT_TRANSITION`

## 8. AI APIs

### POST /api/v1/ai/chat
- Purpose: answer business questions using structured system data only
- Rule: no vector database, no heavy RAG

Request:
```json
{
  "store_id": "store_001",
  "chat_session_id": "chat_001",
  "query": "Why are biscuit sales low this week?"
}
```

Response `200`:
```json
{
  "request_id": "req_ai_001",
  "chat_session_id": "chat_001",
  "analytics_last_updated_at": "2026-04-02T10:45:00Z",
  "freshness_status": "fresh",
  "answer": "Biscuit sales are low this week because the 7-day quantity sold is down 22 percent compared to the previous week. There is also an active NOT_SELLING alert for the product.",
  "grounding": {
    "analytics_used": true,
    "alerts_used": [
      "alert_013"
    ],
    "inventory_products_used": [
      "prod_biscuit_01"
    ]
  }
}
```

Error cases:
- `400 INVALID_REQUEST`
- `503 AI_CONTEXT_NOT_READY`
- `503 AI_PROVIDER_ERROR`

### GET /api/v1/ai/chat/sessions/{chat_session_id}
- Purpose: fetch recent chat history for one session

Response `200`:
```json
{
  "request_id": "req_ai_002",
  "chat_session_id": "chat_001",
  "messages": [
    {
      "role": "user",
      "text": "Why are biscuit sales low this week?",
      "created_at": "2026-04-02T10:50:00Z"
    },
    {
      "role": "assistant",
      "text": "Biscuit sales are low this week because the 7-day quantity sold is down 22 percent.",
      "created_at": "2026-04-02T10:50:02Z"
    }
  ]
}
```

Error cases:
- `404 CHAT_SESSION_NOT_FOUND`

## 9. Data Pipeline APIs

### POST /api/v1/pipeline/runs/sync
- Purpose: trigger an incremental sync manually
- Access: admin only

Request:
```json
{
  "store_id": "store_001",
  "trigger_mode": "manual"
}
```

Response `202`:
```json
{
  "request_id": "req_pipe_001",
  "pipeline_run_id": "pipe_run_001",
  "status": "QUEUED"
}
```

Error cases:
- `401 UNAUTHORIZED`
- `409 PIPELINE_ALREADY_RUNNING`

### GET /api/v1/pipeline/runs/{pipeline_run_id}
- Purpose: fetch pipeline run status

Response `200`:
```json
{
  "request_id": "req_pipe_002",
  "pipeline_run": {
    "pipeline_run_id": "pipe_run_001",
    "status": "FAILED",
    "attempt_count": 3,
    "started_at": "2026-04-02T10:45:00Z",
    "finished_at": "2026-04-02T10:52:00Z",
    "failure_stage": "LOAD_TO_BIGQUERY",
    "error_message": "BigQuery load job timed out"
  }
}
```

Error cases:
- `404 PIPELINE_RUN_NOT_FOUND`

### GET /api/v1/pipeline/failures
- Purpose: list exhausted-retry failures

Response `200`:
```json
{
  "request_id": "req_pipe_003",
  "items": [
    {
      "failure_id": "pf_001",
      "pipeline_run_id": "pipe_run_001",
      "source_module": "Billing",
      "retry_count": 3,
      "dead_letter_status": "OPEN",
      "created_at": "2026-04-02T10:52:00Z"
    }
  ]
}
```

Error cases:
- `401 UNAUTHORIZED`

## 10. API Platform Endpoints

### GET /api/v1/health
- Purpose: liveness check

Response `200`:
```json
{
  "status": "ok"
}
```

### GET /api/v1/ready
- Purpose: readiness check for Firestore, BigQuery, and Gemini dependencies

Response `200`:
```json
{
  "status": "ready",
  "dependencies": {
    "firestore": "ok",
    "bigquery": "ok",
    "gemini": "ok"
  }
}
```

### GET /api/v1/me
- Purpose: current authenticated user profile

Response `200`:
```json
{
  "request_id": "req_api_001",
  "user": {
    "user_id": "user_001",
    "role": "admin",
    "store_id": "store_001"
  }
}
```

## 11. Frontend Module Note
- Frontend Module does not expose REST APIs in this system.
- It consumes the contracts above and displays stock, billing, analytics, alerts, and AI chat.
