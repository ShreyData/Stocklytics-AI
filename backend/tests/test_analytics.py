"""
Analytics Module – Test suite.

Coverage:
    - Happy path: successfully fetch analytics data
    - Failure path: metadata not ready (503)
    - Validates freshness headers are present
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)
AUTH_HEADER = {"Authorization": "Bearer dev-token"}
STORE_ID = "store_001"

MOCK_METADATA = {
    "analytics_last_updated_at": "2026-04-02T10:45:00Z",
    "freshness_status": "fresh"
}

MOCK_DASHBOARD_SUMMARY = {
    "today_sales": 100.0,
    "today_transactions": 5,
    "active_alert_count": 2,
    "low_stock_count": 1,
    "top_selling_product": "Widget"
}


class TestAnalyticsAPI:
    def test_dashboard_success(self):
        with (
            patch("app.modules.analytics.repository.AnalyticsRepository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_dashboard_summary", new_callable=AsyncMock, return_value=MOCK_DASHBOARD_SUMMARY),
        ):
            response = client.get("/api/v1/analytics/dashboard", headers=AUTH_HEADER)
        
        assert response.status_code == 200
        body = response.json()
        assert "request_id" in body
        assert body["analytics_last_updated_at"] == "2026-04-02T10:45:00Z"
        assert body["freshness_status"] == "fresh"
        assert body["summary"]["today_sales"] == 100.0

    def test_analytics_not_ready_if_no_metadata(self):
        with patch("app.modules.analytics.repository.AnalyticsRepository.get_analytics_metadata", new_callable=AsyncMock, return_value=None):
            response = client.get("/api/v1/analytics/dashboard", headers=AUTH_HEADER)
        
        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "ANALYTICS_NOT_READY"

    def test_sales_trends_success(self):
        mock_trends = [{"label": "2026-04-01", "sales_amount": 50.0, "transactions": 2}]
        with (
            patch("app.modules.analytics.repository.AnalyticsRepository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_sales_trends", new_callable=AsyncMock, return_value=mock_trends),
        ):
            response = client.get("/api/v1/analytics/sales-trends", headers=AUTH_HEADER)
            
        assert response.status_code == 200
        body = response.json()
        assert body["points"] == mock_trends

    def test_sales_trends_invalid_range_returns_400_invalid_query(self):
        response = client.get(
            "/api/v1/analytics/sales-trends?range=5d",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "INVALID_QUERY"

    def test_sales_trends_invalid_granularity_returns_400_invalid_query(self):
        response = client.get(
            "/api/v1/analytics/sales-trends?granularity=monthly",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "INVALID_QUERY"

    def test_sales_trends_store_scope_mismatch_returns_400_invalid_query(self):
        response = client.get(
            "/api/v1/analytics/sales-trends?store_id=store_999",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "INVALID_QUERY"

    def test_product_performance_success(self):
        mock_items = [{"product_id": "p1", "product_name": "A", "quantity_sold": 10, "revenue": 100.0}]
        with (
            patch("app.modules.analytics.repository.AnalyticsRepository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_product_performance", new_callable=AsyncMock, return_value=mock_items),
        ):
            response = client.get("/api/v1/analytics/product-performance", headers=AUTH_HEADER)
            
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == mock_items

    def test_customer_insights_success(self):
        mock_customers = [{"customer_id": "c1", "name": "John", "lifetime_spend": 500.0, "visit_count": 10}]
        with (
            patch("app.modules.analytics.repository.AnalyticsRepository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_customer_insights", new_callable=AsyncMock, return_value=mock_customers),
        ):
            response = client.get("/api/v1/analytics/customer-insights", headers=AUTH_HEADER)
            
        assert response.status_code == 200
        body = response.json()
        assert body["top_customers"] == mock_customers
