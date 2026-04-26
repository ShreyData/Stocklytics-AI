"""
Analytics Module – Test suite.

Coverage:
    - Happy path: successfully fetch analytics data
    - Failure path: metadata not ready (503)
    - Validates freshness headers are present
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.modules.analytics.service import AnalyticsService

client = TestClient(app, raise_server_exceptions=False)
AUTH_HEADER = {"Authorization": "Bearer dev-token"}
STORE_ID = "store_001"

MOCK_METADATA = {
    "analytics_last_updated_at": "2100-01-01T00:00:00Z",
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
        assert body["analytics_last_updated_at"] == "2100-01-01T00:00:00Z"
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
        assert "analytics_last_updated_at" in body
        assert "freshness_status" in body
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
        assert "analytics_last_updated_at" in body
        assert "freshness_status" in body
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
        assert "analytics_last_updated_at" in body
        assert "freshness_status" in body
        assert body["top_customers"] == mock_customers

    def test_customer_insights_returns_empty_list_when_mart_has_no_rows(self):
        with (
            patch("app.modules.analytics.repository.AnalyticsRepository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_customer_insights", new_callable=AsyncMock, return_value=[]),
        ):
            response = client.get("/api/v1/analytics/customer-insights", headers=AUTH_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert body["top_customers"] == []
        assert body["freshness_status"] == "fresh"

    def test_dashboard_freshness_becomes_delayed_by_timestamp_age(self):
        delayed_metadata = {
            "analytics_last_updated_at": "2026-04-02T11:15:00+00:00",
            "freshness_status": "fresh",
        }
        fixed_now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
        with (
            patch.object(AnalyticsService, "_utcnow", return_value=fixed_now),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_analytics_metadata", new_callable=AsyncMock, return_value=delayed_metadata),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_dashboard_summary", new_callable=AsyncMock, return_value=MOCK_DASHBOARD_SUMMARY),
        ):
            response = client.get("/api/v1/analytics/dashboard", headers=AUTH_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert body["freshness_status"] == "delayed"

    def test_dashboard_freshness_becomes_stale_by_timestamp_age(self):
        stale_metadata = {
            "analytics_last_updated_at": "2026-04-02T07:30:00+00:00",
            "freshness_status": "fresh",
        }
        fixed_now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
        with (
            patch.object(AnalyticsService, "_utcnow", return_value=fixed_now),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_analytics_metadata", new_callable=AsyncMock, return_value=stale_metadata),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_dashboard_summary", new_callable=AsyncMock, return_value=MOCK_DASHBOARD_SUMMARY),
        ):
            response = client.get("/api/v1/analytics/dashboard", headers=AUTH_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert body["freshness_status"] == "stale"
