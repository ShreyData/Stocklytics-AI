"""
AI Module – Test suite.

Coverage:
    - Happy path: successful chat response with grounding and freshness
    - Graceful degradation when context reads fail
    - Graceful degradation when model provider fails
    - Happy path: session history retrieval
    - Failure path: CHAT_SESSION_NOT_FOUND (404) for missing session
    - Auth: 401 for missing token
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.modules.ai.service import (
    AIService,
    _build_fallback_answer,
    _build_operator_answer,
    _generation_model_candidates,
    _generate_model_answer,
    _infer_analytics_used,
)

client = TestClient(app, raise_server_exceptions=False)
AUTH_HEADER = {"Authorization": "Bearer dev-token"}

VALID_PAYLOAD = {
    "store_id": "store_001",
    "chat_session_id": "chat_001",
    "query": "Why are biscuit sales low this week?",
}

_FRESH_METADATA_TS = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

MOCK_METADATA = {
    "analytics_last_updated_at": _FRESH_METADATA_TS,
    "freshness_status": "fresh",
}

MOCK_ANALYTICS_CONTEXT = {
    "dashboard_summary": {
        "snapshot_date": "2026-04-02",
        "today_sales": 12450.0,
        "today_transactions": 81,
        "active_alert_count": 3,
        "low_stock_count": 2,
        "top_selling_product": "Rice 5kg",
        "analytics_last_updated_at": "2026-04-02T10:45:00Z",
    },
    "sales_trends": [
        {
            "sales_date": "2026-04-02",
            "total_sales": 12450.0,
            "transaction_count": 81,
            "average_basket_value": 153.7,
        },
        {
            "sales_date": "2026-04-01",
            "total_sales": 11800.0,
            "transaction_count": 77,
            "average_basket_value": 153.2,
        },
    ],
    "product_performance": [
        {
            "product_id": "prod_biscuit_01",
            "product_name": "Biscuit Pack",
            "quantity_sold": 12,
            "revenue": 240.0,
            "sales_date": "2026-04-02",
        }
    ],
    "customer_insights": [],
}

MOCK_ALERTS = [
    {
        "alert_id": "alert_013",
        "alert_type": "NOT_SELLING",
        "severity": "HIGH",
        "title": "Biscuit not selling",
        "message": "No sales in 7 days.",
    }
]

MOCK_INVENTORY = [
    {
        "product_id": "prod_biscuit_01",
        "name": "Biscuit Pack",
        "category": "Snacks",
        "quantity_on_hand": 50,
        "price": 20.0,
        "reorder_threshold": 10,
        "expiry_status": "OK",
        "status": "ACTIVE",
        "created_at": "2026-04-01T09:05:00Z",
        "updated_at": "2026-04-02T10:00:00Z",
    }
]

MOCK_GEMINI_ANSWER = (
    "Biscuit sales are low this week because the 7-day quantity sold is down. "
    "There is also an active NOT_SELLING alert for the product."
)


def _mock_gemini(answer: str = MOCK_GEMINI_ANSWER):
    """Return a mock Gemini model whose generate_content returns a fixed answer."""
    mock_response = MagicMock()
    mock_response.text = answer
    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response
    return mock_model


class TestPostChat:
    def test_returns_200_with_answer(self):
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=MOCK_ALERTS),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=MOCK_INVENTORY),
            patch("app.modules.ai.repository.get_customer_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_recent_transactions_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._embed_query", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.vector_search_products", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.service._generate_model_answer", new_callable=AsyncMock, return_value=MOCK_GEMINI_ANSWER),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.ensure_chat_session", new_callable=AsyncMock),
            patch("app.modules.ai.repository.append_message", new_callable=AsyncMock),
        ):
            response = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert "request_id" in body
        assert body["chat_session_id"] == "chat_001"
        assert body["analytics_last_updated_at"] == _FRESH_METADATA_TS
        assert body["freshness_status"] == "fresh"
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0

    def test_returns_grounding_metadata(self):
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=MOCK_ALERTS),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=MOCK_INVENTORY),
            patch("app.modules.ai.repository.get_customer_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_recent_transactions_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._embed_query", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.vector_search_products", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.service._generate_model_answer", new_callable=AsyncMock, return_value=MOCK_GEMINI_ANSWER),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.ensure_chat_session", new_callable=AsyncMock),
            patch("app.modules.ai.repository.append_message", new_callable=AsyncMock),
        ):
            body = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()

        grounding = body["grounding"]
        assert grounding["analytics_used"] is True
        assert "alert_013" in grounding["alerts_used"]
        assert "prod_biscuit_01" in grounding["inventory_products_used"]

    def test_stale_data_uses_separate_freshness_fields_without_appending_warning(self):
        stale_metadata = {**MOCK_METADATA, "freshness_status": "stale"}
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=stale_metadata),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_customer_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_recent_transactions_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._embed_query", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.vector_search_products", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.service._generate_model_answer", new_callable=AsyncMock, return_value=MOCK_GEMINI_ANSWER),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.ensure_chat_session", new_callable=AsyncMock),
            patch("app.modules.ai.repository.append_message", new_callable=AsyncMock),
        ):
            body = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()

        assert body["freshness_status"] == "stale"
        assert "freshness status" not in body["answer"].lower()
        assert "latest available snapshot" not in body["answer"].lower()
        assert "analytics data is not current" not in body["answer"].lower()

    def test_returns_200_when_metadata_missing_using_synthetic_freshness(self):
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_customer_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_recent_transactions_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._embed_query", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.vector_search_products", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.service._generate_model_answer", new_callable=AsyncMock, return_value=MOCK_GEMINI_ANSWER),
        ):
            response = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert body["freshness_status"] in {"fresh", "delayed", "stale"}
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0

    def test_returns_200_when_model_provider_fails_using_fallback(self):
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_customer_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_recent_transactions_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._embed_query", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.vector_search_products", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.service._generate_model_answer", new_callable=AsyncMock, side_effect=Exception("Gemini timeout")),
        ):
            response = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0

    def test_requires_auth(self):
        response = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD)
        assert response.status_code == 401

    def test_rejects_store_scope_mismatch(self):
        bad_payload = {**VALID_PAYLOAD, "store_id": "store_other"}
        response = client.post("/api/v1/ai/chat", json=bad_payload, headers=AUTH_HEADER)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"

    def test_rejects_empty_query(self):
        bad_payload = {**VALID_PAYLOAD, "query": ""}
        response = client.post("/api/v1/ai/chat", json=bad_payload, headers=AUTH_HEADER)
        assert response.status_code == 400

    def test_returns_200_when_analytics_summary_missing_using_live_fallback(self):
        empty_context = {
            "dashboard_summary": None,
            "sales_trends": [],
            "product_performance": [],
            "customer_insights": [],
        }
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_customer_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_recent_transactions_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=empty_context),
            patch("app.modules.ai.service._get_live_dashboard_summary_fallback", new_callable=AsyncMock, return_value=(MOCK_ANALYTICS_CONTEXT["dashboard_summary"], False)),
            patch("app.modules.ai.service._embed_query", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.vector_search_products", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.service._generate_model_answer", new_callable=AsyncMock, return_value=MOCK_GEMINI_ANSWER),
        ):
            response = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER)

        assert response.status_code == 200
        assert isinstance(response.json()["answer"], str)

    def test_persists_messages_to_session(self):
        append_mock = AsyncMock()
        ensure_session_mock = AsyncMock()
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_customer_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_recent_transactions_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._embed_query", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.vector_search_products", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.service._generate_model_answer", new_callable=AsyncMock, return_value=MOCK_GEMINI_ANSWER),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.ensure_chat_session", ensure_session_mock),
            patch("app.modules.ai.repository.append_message", append_mock),
        ):
            client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER)

        assert ensure_session_mock.await_count == 1
        assert ensure_session_mock.await_args.kwargs["store_id"] == "store_001"
        assert ensure_session_mock.await_args.kwargs["user_id"] == "dev_user_001"
        # Should be called twice: once for user message, once for assistant message
        assert append_mock.await_count == 2
        roles = [call.kwargs["role"] for call in append_mock.await_args_list]
        assert roles == ["user", "assistant"]

    def test_returns_answer_even_when_persistence_fails(self):
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_customer_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_recent_transactions_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._embed_query", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.vector_search_products", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.service._generate_model_answer", new_callable=AsyncMock, return_value=MOCK_GEMINI_ANSWER),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, side_effect=RuntimeError("firestore read failed")),
        ):
            body = asyncio.run(
                AIService().chat(
                    store_id="store_001",
                    user_id="dev_user_001",
                    chat_session_id="chat_001",
                    query="Why are biscuit sales low this week?",
                )
            )

        assert body["chat_session_id"] == "chat_001"
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0

    def test_returns_answer_when_firestore_context_reads_fail(self):
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, side_effect=RuntimeError("metadata unavailable")),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, side_effect=RuntimeError("alerts unavailable")),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, side_effect=RuntimeError("inventory unavailable")),
            patch("app.modules.ai.repository.get_customer_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_recent_transactions_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._embed_query", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.vector_search_products", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.service._generate_model_answer", new_callable=AsyncMock, return_value=MOCK_GEMINI_ANSWER),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, side_effect=RuntimeError("firestore read failed")),
        ):
            body = asyncio.run(
                AIService().chat(
                    store_id="store_001",
                    user_id="dev_user_001",
                    chat_session_id="chat_001",
                    query="low stock product",
                )
            )

        assert body["chat_session_id"] == "chat_001"
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0


class TestGetChatSession:
    def test_returns_200_with_messages(self):
        mock_session = {"store_id": "store_001", "chat_session_id": "chat_001"}
        mock_messages = [
            {"role": "user", "text": "Why are biscuit sales low?", "created_at": "2026-04-02T10:50:00Z"},
            {"role": "assistant", "text": "Biscuit sales are low due to an active alert.", "created_at": "2026-04-02T10:50:02Z"},
        ]
        with (
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=mock_session),
            patch("app.modules.ai.repository.list_messages", new_callable=AsyncMock, return_value=mock_messages),
        ):
            response = client.get("/api/v1/ai/chat/sessions/chat_001", headers=AUTH_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert body["chat_session_id"] == "chat_001"
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][1]["role"] == "assistant"

    def test_returns_404_for_missing_session(self):
        with patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=None):
            response = client.get("/api/v1/ai/chat/sessions/chat_missing", headers=AUTH_HEADER)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"

    def test_returns_404_for_session_from_other_store(self):
        other_store_session = {"store_id": "store_other", "chat_session_id": "chat_001"}
        with patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=other_store_session):
            response = client.get("/api/v1/ai/chat/sessions/chat_001", headers=AUTH_HEADER)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"

    def test_requires_auth(self):
        response = client.get("/api/v1/ai/chat/sessions/chat_001")
        assert response.status_code == 401


class TestAIFallbackAnswer:
    def test_handles_blank_inventory_quantities_without_crashing(self):
        answer = _build_fallback_answer(
            query="Which stock items need attention?",
            analytics_summary="today_sales=100; today_transactions=2",
            analytics_context={"dashboard_summary": {}},
            alerts=[],
            inventory=[
                {"product_id": "p1", "name": "Amul Gold 500ml", "quantity_on_hand": ""},
                {"product_id": "p2", "name": "Bread", "quantity_on_hand": None},
            ],
            customers=[],
            transactions=[],
            freshness_status="fresh",
        )

        assert "inventory snapshot" in answer
        assert "Amul Gold 500ml" in answer

    def test_describes_newest_product_from_inventory_context(self):
        answer = _build_operator_answer(
            query="Tell about new product added in inventory",
            analytics_context={"dashboard_summary": {}},
            alerts=[],
            inventory=[
                {
                    "product_id": "prod_old",
                    "name": "Rice 5kg",
                    "category": "Grocery",
                    "price": 320,
                    "quantity_on_hand": 18,
                    "reorder_threshold": 10,
                    "expiry_status": "OK",
                    "status": "ACTIVE",
                    "created_at": "2026-04-01T09:00:00Z",
                    "updated_at": "2026-04-01T09:00:00Z",
                },
                {
                    "product_id": "prod_new",
                    "name": "Amul Gold 500ml",
                    "category": "Dairy",
                    "price": 35,
                    "quantity_on_hand": 5,
                    "reorder_threshold": 8,
                    "expiry_status": "EXPIRING_SOON",
                    "status": "ACTIVE",
                    "created_at": "2026-04-26T09:30:00Z",
                    "updated_at": "2026-04-26T09:30:00Z",
                },
            ],
            customers=[],
            transactions=[],
        )

        assert answer is not None
        assert "Amul Gold 500ml" in answer
        assert "newest product" in answer
        assert "needs replenishment planning" in answer

    def test_inventory_status_answer_highlights_risks_and_next_step(self):
        answer = _build_operator_answer(
            query="Tell current inventory status",
            analytics_context={"dashboard_summary": {}},
            alerts=[
                {
                    "alert_id": "alert_1",
                    "title": "Low Stock: Butter Biscuit",
                    "status": "ACTIVE",
                }
            ],
            inventory=[
                {
                    "product_id": "prod_1",
                    "name": "Butter Biscuit",
                    "quantity_on_hand": 6,
                    "reorder_threshold": 8,
                    "expiry_status": "EXPIRING_SOON",
                    "status": "ACTIVE",
                },
                {
                    "product_id": "prod_2",
                    "name": "Milk 1L",
                    "quantity_on_hand": 0,
                    "reorder_threshold": 6,
                    "expiry_status": "EXPIRED",
                    "status": "ACTIVE",
                },
            ],
            customers=[],
            transactions=[],
        )

        assert answer is not None
        assert "2 active products" in answer
        assert "Top attention items" in answer
        assert "Best next move" in answer

    def test_customer_question_is_answered_from_customer_data(self):
        answer = _build_operator_answer(
            query="Tell about my best customers",
            analytics_context={"dashboard_summary": {}, "customer_insights": []},
            alerts=[],
            inventory=[],
            customers=[
                {
                    "customer_id": "cust_001",
                    "name": "Ravi Kumar",
                    "total_spend": 3140,
                    "visit_count": 9,
                    "last_purchase_at": "2026-04-25T13:45:00Z",
                },
                {
                    "customer_id": "cust_002",
                    "name": "Asha Patel",
                    "total_spend": 1860,
                    "visit_count": 5,
                    "last_purchase_at": "2026-04-24T11:20:00Z",
                },
            ],
            transactions=[],
        )

        assert answer is not None
        assert "Your top customers right now are" in answer
        assert "Ravi Kumar" in answer
        assert "Best next move" in answer

    def test_inventory_question_does_not_mark_analytics_as_used(self):
        analytics_used = _infer_analytics_used(
            query="Tell about new product in inventory",
            answer="The newest product I can see is Maida in Groceries, added today.",
            operator_analytics_used=False,
        )

        assert analytics_used is False


class TestAIModelTransport:
    def test_generate_model_answer_uses_rest_response_text(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "Model answer from REST"}
                                ]
                            }
                        }
                    ]
                }

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                return FakeResponse()

        with (
            patch("app.modules.ai.service.httpx.AsyncClient", FakeClient),
            patch("app.modules.ai.service.get_settings") as settings_mock,
        ):
            settings_mock.return_value.gemini_api_key = "test-key"
            settings_mock.return_value.ai_primary_model_id = "gemini-2.0-flash"
            settings_mock.return_value.ai_default_model_id = "gemini-2.0-flash"
            settings_mock.return_value.ai_reasoning_model_id = "gemini-2.0-flash"
            settings_mock.return_value.gemini_model_fallbacks = []
            settings_mock.return_value.gemini_generation_retries = 0
            settings_mock.return_value.gemini_model_timeout_seconds = 10
            answer = asyncio.run(_generate_model_answer("hello"))

        assert answer == "Model answer from REST"

    def test_generation_model_candidates_deduplicates_primary_and_fallbacks(self):
        candidates = _generation_model_candidates(
            "gemini-2.0-flash",
            ["gemini-2.0-flash", "gemini-2.0-flash-lite-001"],
        )

        assert candidates == ["gemini-2.0-flash", "gemini-2.0-flash-lite-001"]

    def test_generate_model_answer_retries_then_uses_fallback_model(self):
        responses = [
            None,
            None,
            None,
        ]

        class FakeResponse:
            def __init__(self, status_code: int, body: dict[str, object]):
                self.status_code = status_code
                self._body = body
                self.request = httpx.Request("POST", "https://example.com")

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"{self.status_code} error",
                        request=self.request,
                        response=self,
                    )
                return None

            def json(self):
                return self._body

        responses[0] = FakeResponse(429, {})
        responses[1] = FakeResponse(404, {})
        responses[2] = FakeResponse(
            200,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Fallback model answer"}]
                        }
                    }
                ]
            },
        )

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                return responses.pop(0)

        with (
            patch("app.modules.ai.service.httpx.AsyncClient", FakeClient),
            patch("app.modules.ai.service.get_settings") as settings_mock,
            patch("app.modules.ai.service._sleep_before_retry", new_callable=AsyncMock),
        ):
            settings_mock.return_value.gemini_api_key = "test-key"
            settings_mock.return_value.ai_primary_model_id = "gemini-2.0-flash"
            settings_mock.return_value.ai_default_model_id = "gemini-2.0-flash"
            settings_mock.return_value.ai_reasoning_model_id = "gemini-2.0-pro"
            settings_mock.return_value.gemini_model_fallbacks = ["gemini-2.0-flash-lite-001"]
            settings_mock.return_value.gemini_generation_retries = 1
            settings_mock.return_value.gemini_model_timeout_seconds = 10
            answer = asyncio.run(_generate_model_answer("hello"))

        assert answer == "Fallback model answer"
