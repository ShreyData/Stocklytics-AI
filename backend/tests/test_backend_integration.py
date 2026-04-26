from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.ai.service import AIService
from app.modules.analytics.service import AnalyticsService
from app.modules.billing import service as billing_service
from app.modules.billing.schemas import TransactionCreateRequest
from app.modules.inventory import service as inventory_service
from app.modules.inventory.schemas import StockAdjustmentRequest

STORE_ID = "store_001"
USER_ID = "dev_user_001"


def _configured_settings() -> SimpleNamespace:
    return SimpleNamespace(is_local=False, firestore_project_id="test-firestore-project")


def _mock_gemini(answer: str = "Use the latest available analytics snapshot.") -> MagicMock:
    mock_response = MagicMock()
    mock_response.text = answer
    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response
    return mock_model


class TestBillingAlertsIntegration:
    @pytest.mark.asyncio
    async def test_successful_billing_schedules_low_stock_hook(self) -> None:
        payload = TransactionCreateRequest(
            store_id=STORE_ID,
            idempotency_key="bill_integration_001",
            customer_id="cust_001",
            payment_method="cash",
            items=[
                {"product_id": "prod_aaa", "quantity": 1},
                {"product_id": "prod_bbb", "quantity": 1},
            ],
        )
        products = {
            "prod_aaa": {
                "product_id": "prod_aaa",
                "store_id": STORE_ID,
                "name": "Widget Alpha",
                "quantity_on_hand": 10,
                "price": 10.0,
                "reorder_threshold": 3,
            },
            "prod_bbb": {
                "product_id": "prod_bbb",
                "store_id": STORE_ID,
                "name": "Widget Beta",
                "quantity_on_hand": 5,
                "price": 20.0,
                "reorder_threshold": 2,
            },
        }
        created_response = {
            "idempotent_replay": False,
            "transaction": {
                "transaction_id": "txn_001",
                "store_id": STORE_ID,
                "customer_id": "cust_001",
                "status": "COMPLETED",
                "payment_method": "cash",
                "total_amount": 30.0,
                "sale_timestamp": "2026-04-15T12:00:00+00:00",
                "items": [],
            },
            "inventory_updates": [
                {"product_id": "prod_aaa", "new_quantity_on_hand": 2},
                {"product_id": "prod_bbb", "new_quantity_on_hand": 1},
            ],
        }

        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=products),
            patch("app.modules.billing.service.repository.create_billing_transaction", new_callable=AsyncMock, return_value=created_response),
            patch("app.modules.billing.service._schedule_low_stock_evaluation") as schedule_mock,
        ):
            result, status_code = await billing_service.create_transaction(
                payload=payload,
                store_id=STORE_ID,
                user_id=USER_ID,
            )

        assert status_code == 201
        assert result["idempotent_replay"] is False
        assert schedule_mock.call_count == 2
        schedule_mock.assert_any_call(
            store_id=STORE_ID,
            product_id="prod_aaa",
            product_name="Widget Alpha",
            current_stock=2,
            reorder_threshold=3,
        )
        schedule_mock.assert_any_call(
            store_id=STORE_ID,
            product_id="prod_bbb",
            product_name="Widget Beta",
            current_stock=1,
            reorder_threshold=2,
        )

    @pytest.mark.asyncio
    async def test_failed_billing_does_not_schedule_low_stock_hook(self) -> None:
        payload = TransactionCreateRequest(
            store_id=STORE_ID,
            idempotency_key="bill_integration_002",
            customer_id=None,
            payment_method="cash",
            items=[{"product_id": "prod_aaa", "quantity": 2}],
        )

        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch(
                "app.modules.billing.service.repository.get_products_by_ids",
                new_callable=AsyncMock,
                return_value={
                    "prod_aaa": {
                        "product_id": "prod_aaa",
                        "store_id": STORE_ID,
                        "name": "Widget Alpha",
                        "quantity_on_hand": 1,
                        "price": 10.0,
                        "reorder_threshold": 3,
                    }
                },
            ),
            patch("app.modules.billing.service._schedule_low_stock_evaluation") as schedule_mock,
        ):
            with pytest.raises(billing_service.InsufficientStockError):
                await billing_service.create_transaction(
                    payload=payload,
                    store_id=STORE_ID,
                    user_id=USER_ID,
                )

        schedule_mock.assert_not_called()


class TestInventoryAlertsIntegration:
    @pytest.mark.asyncio
    async def test_stock_adjustment_schedules_low_stock_hook_with_product_context(self) -> None:
        payload = StockAdjustmentRequest(
            store_id=STORE_ID,
            adjustment_type="REMOVE",
            quantity_delta=1,
            reason="Manual test removal",
        )

        with (
            patch("app.modules.inventory.service.get_settings", return_value=_configured_settings()),
            patch(
                "app.modules.inventory.service.repository.apply_stock_adjustment_atomic",
                new_callable=AsyncMock,
                return_value=(datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc), 2),
            ),
            patch(
                "app.modules.inventory.service.repository.get_product_by_id",
                new_callable=AsyncMock,
                return_value={
                    "product_id": "prod_aaa",
                    "store_id": STORE_ID,
                    "name": "Widget Alpha",
                    "reorder_threshold": 3,
                },
            ),
            patch("app.modules.inventory.service._schedule_low_stock_evaluation") as schedule_mock,
        ):
            result = await inventory_service.apply_stock_adjustment(
                product_id="prod_aaa",
                payload=payload,
                store_id=STORE_ID,
                user_id=USER_ID,
            )

        assert result["new_quantity_on_hand"] == 2
        schedule_mock.assert_called_once_with(
            store_id=STORE_ID,
            product_id="prod_aaa",
            product_name="Widget Alpha",
            current_stock=2,
            reorder_threshold=3,
        )


class TestAnalyticsAiIntegration:
    @pytest.mark.asyncio
    async def test_ai_and_analytics_share_same_freshness_truth(self) -> None:
        stale_ts = (
            datetime.now(timezone.utc) - timedelta(hours=3)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        metadata = {
            "analytics_last_updated_at": stale_ts,
            "freshness_status": "fresh",
        }
        dashboard_summary = {
            "today_sales": 100.0,
            "today_transactions": 5,
            "active_alert_count": 2,
            "low_stock_count": 1,
            "top_selling_product": "Widget Alpha",
        }
        analytics_context = {
            "dashboard_summary": dashboard_summary,
            "sales_trends": [],
            "product_performance": [],
            "customer_insights": [],
        }

        analytics_service = AnalyticsService()
        ai_service = AIService()

        with (
            patch("app.modules.analytics.repository.AnalyticsRepository.get_analytics_metadata", new_callable=AsyncMock, return_value=metadata),
            patch("app.modules.analytics.repository.AnalyticsRepository.get_dashboard_summary", new_callable=AsyncMock, return_value=dashboard_summary),
        ):
            analytics_result = await analytics_service.get_dashboard_summary(STORE_ID)

        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=metadata),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=analytics_context),
            patch("app.modules.ai.service._get_gemini_model", return_value=_mock_gemini()),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.ensure_chat_session", new_callable=AsyncMock),
            patch("app.modules.ai.repository.append_message", new_callable=AsyncMock),
        ):
            ai_result = await ai_service.chat(
                store_id=STORE_ID,
                user_id=USER_ID,
                chat_session_id="chat_integration_001",
                query="What should I focus on today?",
            )

        assert analytics_result["freshness_status"] == "stale"
        assert ai_result["freshness_status"] == "stale"
        assert "stale" in ai_result["answer"]
