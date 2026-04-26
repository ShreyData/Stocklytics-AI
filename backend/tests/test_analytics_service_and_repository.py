from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.analytics.repository import AnalyticsRepository
from app.modules.analytics.service import AnalyticsNotReadyError, AnalyticsService


_MOCK_SUMMARY = {
    "today_sales": 100.0,
    "today_transactions": 5,
    "active_alert_count": 2,
    "low_stock_count": 1,
    "top_selling_product": "Widget",
}


@pytest.mark.asyncio
async def test_dashboard_freshness_fresh() -> None:
    service = AnalyticsService()
    service.repo = AsyncMock()
    service.repo.get_analytics_metadata.return_value = {
        "analytics_last_updated_at": "2026-04-02T11:45:00+00:00",
        "freshness_status": "fresh",
    }
    service.repo.get_dashboard_summary.return_value = _MOCK_SUMMARY

    with patch.object(
        AnalyticsService,
        "_utcnow",
        return_value=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
    ):
        response = await service.get_dashboard_summary("store_001")

    assert response["freshness_status"] == "fresh"


@pytest.mark.asyncio
async def test_dashboard_freshness_delayed() -> None:
    service = AnalyticsService()
    service.repo = AsyncMock()
    service.repo.get_analytics_metadata.return_value = {
        "analytics_last_updated_at": "2026-04-02T11:15:00+00:00",
        "freshness_status": "fresh",
    }
    service.repo.get_dashboard_summary.return_value = _MOCK_SUMMARY

    with patch.object(
        AnalyticsService,
        "_utcnow",
        return_value=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
    ):
        response = await service.get_dashboard_summary("store_001")

    assert response["freshness_status"] == "delayed"


@pytest.mark.asyncio
async def test_dashboard_freshness_stale() -> None:
    service = AnalyticsService()
    service.repo = AsyncMock()
    service.repo.get_analytics_metadata.return_value = {
        "analytics_last_updated_at": "2026-04-02T07:30:00+00:00",
        "freshness_status": "fresh",
    }
    service.repo.get_dashboard_summary.return_value = _MOCK_SUMMARY

    with patch.object(
        AnalyticsService,
        "_utcnow",
        return_value=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
    ):
        response = await service.get_dashboard_summary("store_001")

    assert response["freshness_status"] == "stale"


@pytest.mark.asyncio
async def test_dashboard_metadata_status_can_force_stricter_freshness() -> None:
    service = AnalyticsService()
    service.repo = AsyncMock()
    service.repo.get_analytics_metadata.return_value = {
        "analytics_last_updated_at": "2026-04-02T11:55:00+00:00",
        "freshness_status": "stale",
    }
    service.repo.get_dashboard_summary.return_value = _MOCK_SUMMARY

    with patch.object(
        AnalyticsService,
        "_utcnow",
        return_value=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
    ):
        response = await service.get_dashboard_summary("store_001")

    assert response["freshness_status"] == "stale"


@pytest.mark.asyncio
async def test_dashboard_not_ready_without_metadata() -> None:
    service = AnalyticsService()
    service.repo = AsyncMock()
    service.repo.get_analytics_metadata.return_value = None

    with pytest.raises(AnalyticsNotReadyError):
        await service.get_dashboard_summary("store_001")


@pytest.mark.asyncio
async def test_dashboard_summary_uses_primary_query_result() -> None:
    repo = AnalyticsRepository()
    row = {
        "today_sales": 120.5,
        "today_transactions": 9,
        "active_alert_count": 7,
        "low_stock_count": 3,
        "top_selling_product": "Rice",
    }

    async def _to_thread_inline(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("app.modules.analytics.repository.asyncio.to_thread", new=AsyncMock(side_effect=_to_thread_inline)),
        patch.object(repo, "_run_query", return_value=[row]) as mock_run_query,
    ):
        summary = await repo.get_dashboard_summary("store_001")

    assert summary is not None
    assert summary["active_alert_count"] == 7
    assert mock_run_query.call_count == 1


@pytest.mark.asyncio
async def test_dashboard_summary_falls_back_when_alert_truth_query_fails() -> None:
    repo = AnalyticsRepository()
    row = {
        "today_sales": 200.0,
        "today_transactions": 12,
        "active_alert_count": 4,
        "low_stock_count": 2,
        "top_selling_product": "Milk",
    }

    async def _to_thread_inline(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("app.modules.analytics.repository.asyncio.to_thread", new=AsyncMock(side_effect=_to_thread_inline)),
        patch.object(repo, "_run_query", side_effect=[Exception("alerts_raw_missing"), [row]]) as mock_run_query,
    ):
        summary = await repo.get_dashboard_summary("store_001")

    assert summary is not None
    assert summary["active_alert_count"] == 4
    assert mock_run_query.call_count == 2
