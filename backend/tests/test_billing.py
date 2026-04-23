"""
Billing Module – Test suite.

Coverage:
    - Happy path: successful transaction creation
    - Failure paths: insufficient stock, missing product, invalid payload
    - Idempotency: replay and conflict handling
    - Read paths: list transactions and fetch one transaction
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

AUTH_HEADER = {"Authorization": "Bearer dev-token"}
STORE_ID = "store_001"
FAKE_NOW = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
FAKE_NOW_ISO = FAKE_NOW.isoformat()

PRODUCT_A = {
    "product_id": "prod_aaa",
    "store_id": STORE_ID,
    "name": "Widget Alpha",
    "quantity_on_hand": 100,
    "price": 10.0,
}
PRODUCT_B = {
    "product_id": "prod_bbb",
    "store_id": STORE_ID,
    "name": "Widget Beta",
    "quantity_on_hand": 5,
    "price": 20.0,
}

VALID_PAYLOAD = {
    "store_id": STORE_ID,
    "idempotency_key": "bill_20260402_0001",
    "customer_id": "cust_001",
    "payment_method": "cash",
    "items": [
        {"product_id": "prod_aaa", "quantity": 10},
        {"product_id": "prod_bbb", "quantity": 2},
    ],
}

CREATED_RESPONSE: dict[str, Any] = {
    "idempotent_replay": False,
    "transaction": {
        "transaction_id": "txn_001",
        "store_id": STORE_ID,
        "customer_id": "cust_001",
        "status": "COMPLETED",
        "payment_method": "cash",
        "total_amount": 140.0,
        "sale_timestamp": FAKE_NOW_ISO,
        "items": [
            {
                "product_id": "prod_aaa",
                "quantity": 10,
                "unit_price": 10.0,
                "line_total": 100.0,
            },
            {
                "product_id": "prod_bbb",
                "quantity": 2,
                "unit_price": 20.0,
                "line_total": 40.0,
            },
        ],
    },
    "inventory_updates": [
        {"product_id": "prod_aaa", "new_quantity_on_hand": 90},
        {"product_id": "prod_bbb", "new_quantity_on_hand": 3},
    ],
}

TRANSACTION_DOC = {
    "transaction_id": "txn_001",
    "store_id": STORE_ID,
    "customer_id": "cust_001",
    "status": "COMPLETED",
    "payment_method": "cash",
    "total_amount": 140.0,
    "sale_timestamp": FAKE_NOW,
    "idempotency_key": "bill_20260402_0001",
    "items": [
        {
            "product_id": "prod_aaa",
            "product_name": "Widget Alpha",
            "quantity": 10,
            "unit_price": 10.0,
            "line_total": 100.0,
        }
    ],
}


def assert_error_shape(body: dict[str, Any]) -> None:
    assert "request_id" in body
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]
    assert "details" in body["error"]


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = {
        "store_id": payload["store_id"],
        "customer_id": payload.get("customer_id"),
        "payment_method": payload["payment_method"],
        "items": sorted(payload["items"], key=lambda item: item["product_id"]),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class TestCreateTransaction:
    def mock_products(self) -> dict[str, dict[str, Any]]:
        return {"prod_aaa": PRODUCT_A, "prod_bbb": PRODUCT_B}

    def test_returns_201_for_new_transaction(self):
        with (
            patch(
                "app.modules.billing.service.repository.get_idempotency_record",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.modules.billing.service.repository.get_products_by_ids",
                new_callable=AsyncMock,
                return_value=self.mock_products(),
            ),
            patch(
                "app.modules.billing.service.repository.create_billing_transaction",
                new_callable=AsyncMock,
                return_value=CREATED_RESPONSE,
            ),
        ):
            response = client.post(
                "/api/v1/billing/transactions",
                json=VALID_PAYLOAD,
                headers=AUTH_HEADER,
            )
        assert response.status_code == 201

    def test_returns_contract_shape(self):
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=self.mock_products()),
            patch("app.modules.billing.service.repository.create_billing_transaction", new_callable=AsyncMock, return_value=CREATED_RESPONSE),
        ):
            body = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()
        assert body["idempotent_replay"] is False
        assert "transaction" in body
        assert "inventory_updates" in body
        assert body["transaction"]["payment_method"] == "cash"

    def test_requires_auth(self):
        response = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD)
        assert response.status_code == 401
        assert_error_shape(response.json())

    def test_rejects_missing_store_id(self):
        bad_payload = {key: value for key, value in VALID_PAYLOAD.items() if key != "store_id"}
        response = client.post("/api/v1/billing/transactions", json=bad_payload, headers=AUTH_HEADER)
        assert response.status_code == 400

    def test_rejects_missing_payment_method(self):
        bad_payload = {key: value for key, value in VALID_PAYLOAD.items() if key != "payment_method"}
        response = client.post("/api/v1/billing/transactions", json=bad_payload, headers=AUTH_HEADER)
        assert response.status_code == 400

    def test_rejects_empty_items(self):
        bad_payload = {**VALID_PAYLOAD, "items": []}
        response = client.post("/api/v1/billing/transactions", json=bad_payload, headers=AUTH_HEADER)
        assert response.status_code == 400

    def test_rejects_zero_quantity(self):
        bad_payload = {
            **VALID_PAYLOAD,
            "items": [{"product_id": "prod_aaa", "quantity": 0}],
        }
        response = client.post("/api/v1/billing/transactions", json=bad_payload, headers=AUTH_HEADER)
        assert response.status_code == 400


class TestBillingFailures:
    def test_returns_409_when_stock_insufficient(self):
        low_stock_products = {
            "prod_aaa": PRODUCT_A,
            "prod_bbb": {**PRODUCT_B, "quantity_on_hand": 1},
        }
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=low_stock_products),
        ):
            response = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD, headers=AUTH_HEADER)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    def test_no_write_called_when_stock_insufficient(self):
        write_mock = AsyncMock()
        low_stock_products = {"prod_aaa": {**PRODUCT_A, "quantity_on_hand": 1}}
        payload = {
            **VALID_PAYLOAD,
            "items": [{"product_id": "prod_aaa", "quantity": 10}],
        }
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value=low_stock_products),
            patch("app.modules.billing.service.repository.create_billing_transaction", write_mock),
        ):
            client.post("/api/v1/billing/transactions", json=payload, headers=AUTH_HEADER)
        write_mock.assert_not_called()

    def test_returns_404_when_product_missing(self):
        payload = {
            **VALID_PAYLOAD,
            "items": [{"product_id": "prod_missing", "quantity": 1}],
        }
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value={}),
        ):
            response = client.post("/api/v1/billing/transactions", json=payload, headers=AUTH_HEADER)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"

    def test_duplicate_line_items_are_aggregated_for_stock_check(self):
        payload = {
            **VALID_PAYLOAD,
            "items": [
                {"product_id": "prod_bbb", "quantity": 3},
                {"product_id": "prod_bbb", "quantity": 3},
            ],
        }
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=None),
            patch("app.modules.billing.service.repository.get_products_by_ids", new_callable=AsyncMock, return_value={"prod_bbb": PRODUCT_B}),
        ):
            response = client.post("/api/v1/billing/transactions", json=payload, headers=AUTH_HEADER)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"


class TestIdempotency:
    def make_idempotency_record(self) -> dict[str, Any]:
        return {
            "idempotency_record_id": f"{STORE_ID}_bill_20260402_0001",
            "store_id": STORE_ID,
            "idempotency_key": "bill_20260402_0001",
            "request_hash": payload_hash(VALID_PAYLOAD),
            "transaction_id": "txn_001",
            "result_status": "COMPLETED",
            "response_snapshot": CREATED_RESPONSE,
            "created_at": FAKE_NOW,
            "last_seen_at": FAKE_NOW,
        }

    def test_same_key_same_payload_returns_200(self):
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=self.make_idempotency_record()),
            patch("app.modules.billing.service.repository.touch_idempotency_record", new_callable=AsyncMock),
        ):
            response = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD, headers=AUTH_HEADER)
        assert response.status_code == 200
        assert response.json()["idempotent_replay"] is True

    def test_same_key_same_payload_returns_summary(self):
        with (
            patch("app.modules.billing.service.repository.get_idempotency_record", new_callable=AsyncMock, return_value=self.make_idempotency_record()),
            patch("app.modules.billing.service.repository.touch_idempotency_record", new_callable=AsyncMock),
        ):
            body = client.post("/api/v1/billing/transactions", json=VALID_PAYLOAD, headers=AUTH_HEADER).json()
        assert body["transaction"]["transaction_id"] == "txn_001"
        assert body["transaction"]["status"] == "COMPLETED"
        assert body["transaction"]["total_amount"] == 140.0

    def test_same_key_different_payload_returns_409(self):
        conflicting_payload = {
            **VALID_PAYLOAD,
            "items": [{"product_id": "prod_aaa", "quantity": 99}],
        }
        with patch(
            "app.modules.billing.service.repository.get_idempotency_record",
            new_callable=AsyncMock,
            return_value=self.make_idempotency_record(),
        ):
            response = client.post("/api/v1/billing/transactions", json=conflicting_payload, headers=AUTH_HEADER)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


class TestReadTransactions:
    def test_list_transactions_returns_items(self):
        transaction_docs = [
            {
                "transaction_id": "txn_001",
                "customer_id": "cust_001",
                "total_amount": 140.0,
                "sale_timestamp": FAKE_NOW,
                "status": "COMPLETED",
            }
        ]
        with patch(
            "app.modules.billing.service.repository.list_transactions",
            new_callable=AsyncMock,
            return_value=transaction_docs,
        ):
            response = client.get("/api/v1/billing/transactions", headers=AUTH_HEADER)
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["next_page_token"] is None

    def test_list_transactions_supports_pagination(self):
        transaction_docs = [
            {
                "transaction_id": "txn_001",
                "customer_id": "cust_001",
                "total_amount": 140.0,
                "sale_timestamp": FAKE_NOW,
                "status": "COMPLETED",
            },
            {
                "transaction_id": "txn_002",
                "customer_id": None,
                "total_amount": 55.0,
                "sale_timestamp": FAKE_NOW,
                "status": "COMPLETED",
            },
        ]
        with patch(
            "app.modules.billing.service.repository.list_transactions",
            new_callable=AsyncMock,
            return_value=transaction_docs,
        ):
            response = client.get("/api/v1/billing/transactions?limit=1", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert response.json()["next_page_token"] == "1"

    def test_get_transaction_returns_detail(self):
        with patch(
            "app.modules.billing.service.repository.get_transaction_by_id",
            new_callable=AsyncMock,
            return_value=TRANSACTION_DOC,
        ):
            response = client.get("/api/v1/billing/transactions/txn_001", headers=AUTH_HEADER)
        assert response.status_code == 200
        body = response.json()
        assert body["transaction"]["transaction_id"] == "txn_001"
        assert body["transaction"]["idempotency_key"] == "bill_20260402_0001"

    def test_get_missing_transaction_returns_404(self):
        with patch(
            "app.modules.billing.service.repository.get_transaction_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.get("/api/v1/billing/transactions/txn_missing", headers=AUTH_HEADER)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"
