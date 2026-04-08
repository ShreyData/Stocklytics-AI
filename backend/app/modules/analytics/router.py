"""
Analytics Module router stub.

Owned by: Analytics Module developer.
Base path: /api/v1/analytics

Planned endpoints (implement per analytics_implementation.md):
    GET  /api/v1/analytics/dashboard
    GET  /api/v1/analytics/sales-trends
    GET  /api/v1/analytics/product-performance
    GET  /api/v1/analytics/customer-insights

Key rules:
    - Every response MUST include analytics_last_updated_at and freshness_status.
    - Do not run analytics computation inside live request paths.
    - Read only from BigQuery mart tables.
"""

from fastapi import APIRouter

router = APIRouter()

# TODO: implement analytics endpoints per analytics_implementation.md and api_contracts.md
