"""
Billing Module – Test suite.

Coverage:
    - Happy path: successful transaction creation (POST /api/v1/billing/transactions)
    - Failure path: insufficient stock → no partial writes
    - Idempotency: replay with same key + payload → 200 with original result
    - Idempotency conflict: same key + different payload → 409

All Firestore I/O is mocked; no external dependencies required.

Run with:
    pytest backend/tests/test_billing.py -v
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

AUTH_HEADER = {"Authorization": "Bearer dev-token"}

# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

FAKE_TXN_ID = "txn_abc123"
FAKE_NOW = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
FAKE_NOW_ISO = FAKE_NOW.isoformat()

PRODUCT_A = {
    "product_id": "prod_aaa",
    "store_id": "store_001",
    "name": "Widget Alpha",
    "quantity_on_hand": 100,
    "price": 10.00,
}

PRODUCT_B = {
    "product_id": "prod_bbb",
    "store_id": "store_001",
    "name": "Widget Beta",
    "quantity_on_hand": 5,
    "price": 20.00,
}

VALID_PAYLOAD = {
    "idempotency_key": "order-2026-001",
    "items": [
        {"product_id": "prod_aaa", "quantity": 10, "unit_price": 10.00},
        {"product_id": "prod_bbb", "quantity": 2, "unit_price": 20.00},
    ],
    "notes": "Test order",
}

STORED_TRANSACTION: dict[str, Any] = {
    "transaction_id": FAKE_TXN_ID,
    "store_id": "store_001",
    "idempotency_key": "order-2026-001",
    "items": [
        {"product_id": "prod_aaa", "quantity": 10, "unit_price": 10.00, "line_total": 100.00},
        {"product_id": "prod_bbb", "quantity": 2, "unit_price": 20.00, "line_total": 40.00},
    ],
    "total_amount": 140.00,
    "status": "COMPLETED",
    "notes": "Test order",
    "created_by": "dev_user_001",
    "created_at": FAKE_NOW_ISO,
}


def assert_error_shape(body: dict) -> None:
    """Assert the shared error response model is present."""
    assert "request_id" in body, "Missing request_id"
    assert "error" in body, "Missing error object"
    assert "code" in body["error"], "Missing error.code"
    assert "message" in body["error"], "Missing error.message"
    assert "details" in body["error"], "Missing error.details"


def _payload_hash(items: list[dict]) -> str:
    """Reproduce the service's payload hash for test assertions."""
    canonical = sorted(items, key=lambda x: x["product_id"])
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Test Class 1: Happy path – successful transaction
# ---------------------------------------------------------------------------

class TestCreateTransactionSuccess:
    """POST /api/v1/billing/transactions – all stock available, new key."""

    def _mock_products(self):
        return {"prod_aaa": PRODUCT_A, "prod_bbb": PRODUCT_B}

    def test_returns_201(self):
        with (
            patch(
                "app.modules.billing.service.repository.get_idempotency_record",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.modules.billing.service.repository.get_products_by_ids",
                new_callable=AsyncMock,
                return_value=self._mock_products(),
            ),
            patch(
                "app.modules.billing.service.repository.create_billing_transaction",
                new_callable=AsyncMock,
                return_value=STORED_TRANSACTION,
            ),
        ):
            response = client.post(
                "/api/v1/billing/transactions",
                json=VALID_PAYLOAD,
                headers=AUTH_HEADER,
            )
        assert response.status_code == 201

    def test_response_contains_request_id(self):
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=self._mock_products()),
            patch("app.modules.billing.service.repository.create_billing_transaction", new_callable=AsyncMock, return_value=STORED_TRANSACTION),
        ):
            body = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()
        assert "request_id" in body

    def test_response_body_shape(self):
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=self._mock_products()),
            patch("app.modules.billing.service.repository.create_billing_transaction", new_callable=AsyncMock, return_value=STORED_TRANSACTION),
        ):
            body = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()
        txn = body["transaction"]
        assert "transaction_id" in txn
        assert "store_id" in txn
        assert "idempotency_key" in txn
        assert "items" in txn
        assert "total_amount" in txn
        assert "status" in txn

    def test_status_is_completed(self):
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=self._mock_products()),
            patch("app.modules.billing.service.repository.create_billing_transaction", new_callable=AsyncMock, return_value=STORED_TRANSACTION),
        ):
            body = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()
        assert body["transaction"]["status"] == "COMPLETED"

    def test_total_amount_is_correct(self):
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=self._mock_products()),
            patch("app.modules.billing.service.repository.create_billing_transaction", new_callable=AsyncMock, return_value=STORED_TRANSACTION),
        ):
            body = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()
        # 10*10 + 2*20 = 140
        assert body["transaction"]["total_amount"] == 140.00

    def test_requires_auth(self):
        response = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD)
        assert response.status_code == 401
        assert_error_shape(response.json())

    def test_rejects_empty_items(self):
        bad_payload = {**VALID_PAYLOAD, "items": []}
        response = client.post("/api/v1/billing/transactions", json=bad_payload, headers=AUTH_HEADER)
        assert response.status_code == 400

    def test_rejects_missing_idempotency_key(self):
        bad_payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "idempotency_key"}
        response = client.post("/api/v1/billing/transactions", json=bad_payload, headers=AUTH_HEADER)
        assert response.status_code == 400

    def test_rejects_zero_quantity(self):
        bad_payload = {
            **VALID_PAYLOAD,
            "idempotency_key": "order-zero-qty",
            "items": [{"product_id": "prod_aaa", "quantity": 0, "unit_price": 10.00}],
        }
        response = client.post("/api/v1/billing/transactions", json=bad_payload, headers=AUTH_HEADER)
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Test Class 2: Insufficient stock – no partial writes
# ---------------------------------------------------------------------------

class TestInsufficientStock:
    """
    Billing must reject the entire request when ANY item lacks sufficient stock.
    No stock should be deducted for items that did have enough stock.
    """

    def test_returns_400_when_stock_insufficient(self):
        """
        prod_bbb has only 5 units but we request 10.
        The whole transaction must fail with 400.
        """
        low_stock_products = {
            "prod_aaa": {**PRODUCT_A, "quantity_on_hand": 100},
            "prod_bbb": {**PRODUCT_B, "quantity_on_hand": 5},   # only 5 available
        }
        payload = {
            "idempotency_key": "order-insufficient",
            "items": [
                {"product_id": "prod_aaa", "quantity": 10, "unit_price": 10.00},
                {"product_id": "prod_bbb", "quantity": 10, "unit_price": 20.00},  # 10 > 5
            ],
        }
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=low_stock_products),
        ):
            response = client.post("/api/v1/billing/transactions", json=payload, headers=AUTH_HEADER)
        assert response.status_code == 400

    def test_error_shape_on_insufficient_stock(self):
        low_stock_products = {
            "prod_aaa": {**PRODUCT_A, "quantity_on_hand": 1},
        }
        payload = {
            "idempotency_key": "order-insuff2",
            "items": [{"product_id": "prod_aaa", "quantity": 50, "unit_price": 10.00}],
        }
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=low_stock_products),
        ):
            response = client.post("/api/v1/billing/transactions", json=payload, headers=AUTH_HEADER)
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "INVALID_REQUEST"

    def test_error_details_include_insufficient_items(self):
        low_stock_products = {"prod_aaa": {**PRODUCT_A, "quantity_on_hand": 3}}
        payload = {
            "idempotency_key": "order-insuff3",
            "items": [{"product_id": "prod_aaa", "quantity": 10, "unit_price": 10.00}],
        }
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=low_stock_products),
        ):
            response = client.post("/api/v1/billing/transactions", json=payload, headers=AUTH_HEADER)
        details = response.json()["error"]["details"]
        assert "insufficient_items" in details
        assert details["insufficient_items"][0]["product_id"] == "prod_aaa"

    def test_firestore_write_not_called_on_insufficient_stock(self):
        """create_billing_transaction must never be called when stock fails."""
        mock_write = AsyncMock()
        low_stock_products = {"prod_aaa": {**PRODUCT_A, "quantity_on_hand": 0}}
        payload = {
            "idempotency_key": "order-nowrite",
            "items": [{"product_id": "prod_aaa", "quantity": 5, "unit_price": 10.00}],
        }
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=low_stock_products),
            patch("app.modules.billing.service.repository.create_billing_transaction", mock_write),
        ):
            client.post("/api/v1/billing/transactions", json=payload, headers=AUTH_HEADER)
        mock_write.assert_not_called()

    def test_missing_product_returns_404(self):
        """A product_id that doesn't exist in the store must return 404."""
        payload = {
            "idempotency_key": "order-missing-prod",
            "items": [{"product_id": "prod_ghost", "quantity": 1, "unit_price": 5.00}],
        }
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value={}),
        ):
            response = client.post("/api/v1/billing/transactions", json=payload, headers=AUTH_HEADER)
        assert response.status_code == 404
        assert_error_shape(response.json())


# ---------------------------------------------------------------------------
# Test Class 3: Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    """
    Same idempotency_key + same payload → return original result (HTTP 200).
    Same idempotency_key + different payload → HTTP 409.
    """

    def _make_idempotency_record(self, items: list[dict]) -> dict[str, Any]:
        """Build the stored idempotency record that the repository would return."""
        canonical = sorted(items, key=lambda x: x["product_id"])
        raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(raw.encode()).hexdigest()
        return {
            "idempotency_key": "order-2026-001",
            "store_id": "store_001",
            "payload_hash": payload_hash,
            "transaction_id": FAKE_TXN_ID,
            "transaction_snapshot": STORED_TRANSACTION,
            "created_at": FAKE_NOW,
        }

    def test_replay_returns_200(self):
        """Re-sending the identical request must return HTTP 200 (not 201)."""
        items = [
            {"product_id": "prod_aaa", "quantity": 10, "unit_price": 10.0},
            {"product_id": "prod_bbb", "quantity": 2, "unit_price": 20.0},
        ]
        idp_record = self._make_idempotency_record(items)
        with patch(
            "app.modules.billing.service.repository.get_idempotency_record",
            new_callable=AsyncMock,
            return_value=idp_record,
        ):
            response = client.post(
                "/api/v1/billing/transactions",
                json=VALID_PAYLOAD,
                headers=AUTH_HEADER,
            )
        assert response.status_code == 200

    def test_replay_returns_original_transaction(self):
        """The replayed response must contain the originally stored transaction."""
        items = [
            {"product_id": "prod_aaa", "quantity": 10, "unit_price": 10.0},
            {"product_id": "prod_bbb", "quantity": 2, "unit_price": 20.0},
        ]
        idp_record = self._make_idempotency_record(items)
        with patch(
            "app.modules.billing.service.repository.get_idempotency_record",
            new_callable=AsyncMock,
            return_value=idp_record,
        ):
            body = client.post(
                "/api/v1/billing/transactions",
                json=VALID_PAYLOAD,
                headers=AUTH_HEADER,
            ).json()
        assert body["transaction"]["transaction_id"] == FAKE_TXN_ID

    def test_replay_does_not_call_write(self):
        """On idempotent replay, create_billing_transaction must NOT be called."""
        items = [
            {"product_id": "prod_aaa", "quantity": 10, "unit_price": 10.0},
            {"product_id": "prod_bbb", "quantity": 2, "unit_price": 20.0},
        ]
        idp_record = self._make_idempotency_record(items)
        mock_write = AsyncMock()
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=idp_record),
            patch("app.modules.billing.service.repository.create_billing_transaction", mock_write),
        ):
            client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD, headers=AUTH_HEADER)
        mock_write.assert_not_called()

    def test_conflict_returns_409_for_different_payload(self):
        """
        Reusing an idempotency_key with a different payload must return 409 CONFLICT.
        """
        # Stored record was for quantity=10; new request sends quantity=99
        original_items = [{"product_id": "prod_aaa", "quantity": 10, "unit_price": 10.0}]
        idp_record = self._make_idempotency_record(original_items)

        conflicting_payload = {
            "idempotency_key": "order-2026-001",  # same key
            "items": [{"product_id": "prod_aaa", "quantity": 99, "unit_price": 10.00}],  # different qty
        }
        with patch(
            "app.modules.billing.service.repository.get_idempotency_record",
            new_callable=AsyncMock,
            return_value=idp_record,
        ):
            response = client.post(
                "/api/v1/billing/transactions",
                json=conflicting_payload,
                headers=AUTH_HEADER,
            )
        assert response.status_code == 409

    def test_conflict_error_shape(self):
        """The 409 response must still follow the shared error envelope."""
        original_items = [{"product_id": "prod_aaa", "quantity": 10, "unit_price": 10.0}]
        idp_record = self._make_idempotency_record(original_items)
        conflicting_payload = {
            "idempotency_key": "order-2026-001",
            "items": [{"product_id": "prod_aaa", "quantity": 1, "unit_price": 5.00}],
        }
        with patch(
            "app.modules.billing.service.repository.get_idempotency_record",
            new_callable=AsyncMock,
            return_value=idp_record,
        ):
            response = client.post(
                "/api/v1/billing/transactions",
                json=conflicting_payload,
                headers=AUTH_HEADER,
            )
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "CONFLICT"
