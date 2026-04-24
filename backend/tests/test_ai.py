"""
AI Module – Test suite.

Coverage:
    - Happy path: successful chat response with grounding and freshness
    - Failure path: AI_CONTEXT_NOT_READY (503) when metadata missing
    - Failure path: AI_PROVIDER_ERROR (503) when Gemini call fails
    - Happy path: session history retrieval
    - Failure path: CHAT_SESSION_NOT_FOUND (404) for missing session
    - Auth: 401 for missing token
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)
AUTH_HEADER = {"Authorization": "Bearer dev-token"}

VALID_PAYLOAD = {
    "store_id": "store_001",
    "chat_session_id": "chat_001",
    "query": "Why are biscuit sales low this week?",
}

MOCK_METADATA = {
    "analytics_last_updated_at": "2026-04-02T10:45:00Z",
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
        "quantity_on_hand": 50,
        "price": 20.0,
        "reorder_threshold": 10,
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
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._get_gemini_model", return_value=_mock_gemini()),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.ensure_chat_session", new_callable=AsyncMock),
            patch("app.modules.ai.repository.append_message", new_callable=AsyncMock),
        ):
            response = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER)

        assert response.status_code == 200
        body = response.json()
        assert "request_id" in body
        assert body["chat_session_id"] == "chat_001"
        assert body["analytics_last_updated_at"] == "2026-04-02T10:45:00Z"
        assert body["freshness_status"] == "fresh"
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0

    def test_returns_grounding_metadata(self):
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=MOCK_ALERTS),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=MOCK_INVENTORY),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._get_gemini_model", return_value=_mock_gemini()),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.ensure_chat_session", new_callable=AsyncMock),
            patch("app.modules.ai.repository.append_message", new_callable=AsyncMock),
        ):
            body = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()

        grounding = body["grounding"]
        assert grounding["analytics_used"] is True
        assert "alert_013" in grounding["alerts_used"]
        assert "prod_biscuit_01" in grounding["inventory_products_used"]

    def test_stale_data_appends_freshness_warning(self):
        stale_metadata = {**MOCK_METADATA, "freshness_status": "stale"}
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=stale_metadata),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._get_gemini_model", return_value=_mock_gemini()),
            patch("app.modules.ai.repository.get_chat_session", new_callable=AsyncMock, return_value=None),
            patch("app.modules.ai.repository.ensure_chat_session", new_callable=AsyncMock),
            patch("app.modules.ai.repository.append_message", new_callable=AsyncMock),
        ):
            body = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()

        assert "stale" in body["answer"]
        assert "⚠️" in body["answer"]

    def test_returns_503_when_metadata_missing(self):
        with patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=None):
            response = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_CONTEXT_NOT_READY"

    def test_returns_503_when_gemini_fails(self):
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._get_gemini_model", side_effect=Exception("Gemini timeout")),
        ):
            response = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_PROVIDER_ERROR"

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

    def test_returns_503_when_analytics_summary_missing(self):
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
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=empty_context),
        ):
            response = client.post("/api/v1/ai/chat", json=VALID_PAYLOAD, headers=AUTH_HEADER)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_CONTEXT_NOT_READY"

    def test_persists_messages_to_session(self):
        append_mock = AsyncMock()
        ensure_session_mock = AsyncMock()
        with (
            patch("app.modules.ai.repository.get_analytics_metadata", new_callable=AsyncMock, return_value=MOCK_METADATA),
            patch("app.modules.ai.repository.get_relevant_alerts_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_inventory_snapshot", new_callable=AsyncMock, return_value=[]),
            patch("app.modules.ai.repository.get_analytics_context", new_callable=AsyncMock, return_value=MOCK_ANALYTICS_CONTEXT),
            patch("app.modules.ai.service._get_gemini_model", return_value=_mock_gemini()),
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
