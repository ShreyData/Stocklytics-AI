"""
Inventory Module – Test suite.

Tests for the Inventory endpoints:
    - Happy path: create product (POST /api/v1/inventory/products)
    - Failure path: negative stock prevention (POST /api/v1/inventory/products/{id}/stock-adjustments)
    - Update path: patch product (PATCH /api/v1/inventory/products/{id})

All tests run against the FastAPI TestClient with Firestore fully mocked
so that no external I/O is required. Dev-token stub auth is used throughout.

Run with:
    pytest backend/tests/test_inventory.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

AUTH_HEADER = {"Authorization": "Bearer dev-token"}

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

FAKE_PRODUCT_ID = "prod_abc123"
FAKE_NOW = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)

SAMPLE_PRODUCT: dict[str, Any] = {
    "product_id": FAKE_PRODUCT_ID,
    "store_id": "store_001",
    "name": "Test Widget",
    "category": "Widgets",
    "price": 9.99,
    "quantity_on_hand": 50,
    "reorder_threshold": 10,
    "expiry_date": None,
    "expiry_status": "OK",
    "status": "ACTIVE",
    "created_at": FAKE_NOW.isoformat(),
    "updated_at": FAKE_NOW.isoformat(),
}

SAMPLE_ADJUSTMENT: dict[str, Any] = {
    "adjustment_id": "adj_def456",
    "store_id": "store_001",
    "product_id": FAKE_PRODUCT_ID,
    "adjustment_type": "ADD",
    "quantity_delta": 20,
    "reason": "Restocking shipment received",
    "source_ref": "PO-2026-001",
    "created_by": "dev_user_001",
    "created_at": FAKE_NOW.isoformat(),
}


def assert_error_shape(body: dict) -> None:
    """Assert the shared error response model is present."""
    assert "request_id" in body, "Missing request_id"
    assert "error" in body, "Missing error object"
    assert "code" in body["error"], "Missing error.code"
    assert "message" in body["error"], "Missing error.message"
    assert "details" in body["error"], "Missing error.details"


# ---------------------------------------------------------------------------
# Test Class 1: Happy path – create product
# ---------------------------------------------------------------------------

class TestCreateProduct:
    """POST /api/v1/inventory/products – successful product creation."""

    def test_create_product_returns_201(self):
        """A valid create request must return 201 Created."""
        with patch(
            "app.modules.inventory.service.repository.create_product",
            new_callable=AsyncMock,
            return_value=SAMPLE_PRODUCT,
        ):
            response = client.post(
                "/api/v1/inventory/products",
                json={
                    "name": "Test Widget",
                    "category": "Widgets",
                    "price": 9.99,
                    "quantity_on_hand": 50,
                    "reorder_threshold": 10,
                },
                headers=AUTH_HEADER,
            )
        assert response.status_code == 201

    def test_create_product_response_contains_request_id(self):
        """Response envelope must always include request_id."""
        with patch(
            "app.modules.inventory.service.repository.create_product",
            new_callable=AsyncMock,
            return_value=SAMPLE_PRODUCT,
        ):
            response = client.post(
                "/api/v1/inventory/products",
                json={
                    "name": "Test Widget",
                    "category": "Widgets",
                    "price": 9.99,
                    "quantity_on_hand": 50,
                    "reorder_threshold": 10,
                },
                headers=AUTH_HEADER,
            )
        body = response.json()
        assert "request_id" in body

    def test_create_product_body_shape(self):
        """Created product must contain all required fields."""
        with patch(
            "app.modules.inventory.service.repository.create_product",
            new_callable=AsyncMock,
            return_value=SAMPLE_PRODUCT,
        ):
            response = client.post(
                "/api/v1/inventory/products",
                json={
                    "name": "Test Widget",
                    "category": "Widgets",
                    "price": 9.99,
                    "quantity_on_hand": 50,
                    "reorder_threshold": 10,
                },
                headers=AUTH_HEADER,
            )
        body = response.json()
        product = body["product"]
        assert "product_id" in product
        assert "store_id" in product
        assert "quantity_on_hand" in product
        assert "expiry_status" in product

    def test_create_product_requires_auth(self):
        """Requests without a Bearer token must receive 401."""
        response = client.post(
            "/api/v1/inventory/products",
            json={
                "name": "Test Widget",
                "category": "Widgets",
                "price": 9.99,
                "quantity_on_hand": 50,
                "reorder_threshold": 10,
            },
        )
        assert response.status_code == 401
        assert_error_shape(response.json())

    def test_create_product_rejects_missing_required_fields(self):
        """Missing required fields must return 400 with error shape."""
        response = client.post(
            "/api/v1/inventory/products",
            json={"name": "Incomplete Widget"},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 400
        assert_error_shape(response.json())

    def test_create_product_rejects_negative_quantity(self):
        """Negative quantity_on_hand must fail Pydantic validation (400)."""
        response = client.post(
            "/api/v1/inventory/products",
            json={
                "name": "Bad Widget",
                "category": "Widgets",
                "price": 5.0,
                "quantity_on_hand": -1,
                "reorder_threshold": 0,
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 400

    def test_create_product_computes_expiry_status_ok(self):
        """Products without expiry_date must return expiry_status=OK."""
        product_no_expiry = {**SAMPLE_PRODUCT, "expiry_date": None, "expiry_status": "OK"}
        with patch(
            "app.modules.inventory.service.repository.create_product",
            new_callable=AsyncMock,
            return_value=product_no_expiry,
        ):
            response = client.post(
                "/api/v1/inventory/products",
                json={
                    "name": "No Expiry Widget",
                    "category": "Widgets",
                    "price": 1.0,
                    "quantity_on_hand": 100,
                    "reorder_threshold": 5,
                },
                headers=AUTH_HEADER,
            )
        body = response.json()
        assert body["product"]["expiry_status"] == "OK"


# ---------------------------------------------------------------------------
# Test Class 2: Failure path – negative stock prevention
# ---------------------------------------------------------------------------

class TestNegativeStockPrevention:
    """POST /api/v1/inventory/products/{id}/stock-adjustments – stock guard."""

    def _existing_product(self, quantity: int = 5) -> dict[str, Any]:
        return {**SAMPLE_PRODUCT, "quantity_on_hand": quantity}

    def test_remove_more_than_stock_returns_400(self):
        """
        Removing more units than available must return 400 with
        INVALID_REQUEST error code – stock must never go negative.
        """
        with patch(
            "app.modules.inventory.service.repository.get_product_by_id",
            new_callable=AsyncMock,
            return_value=self._existing_product(quantity=5),
        ):
            response = client.post(
                f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}/stock-adjustments",
                json={
                    "adjustment_type": "REMOVE",
                    "quantity_delta": 10,   # 10 > 5 available → must reject
                    "reason": "Manual removal attempt",
                },
                headers=AUTH_HEADER,
            )
        assert response.status_code == 400
        body = response.json()
        assert_error_shape(body)
        assert body["error"]["code"] == "INVALID_REQUEST"

    def test_sale_deduction_exceeding_stock_returns_400(self):
        """SALE_DEDUCTION that results in negative stock must be rejected."""
        with patch(
            "app.modules.inventory.service.repository.get_product_by_id",
            new_callable=AsyncMock,
            return_value=self._existing_product(quantity=3),
        ):
            response = client.post(
                f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}/stock-adjustments",
                json={
                    "adjustment_type": "SALE_DEDUCTION",
                    "quantity_delta": 5,  # 5 > 3 → must reject
                    "reason": "Point-of-sale deduction",
                },
                headers=AUTH_HEADER,
            )
        assert response.status_code == 400
        assert_error_shape(response.json())

    def test_exact_stock_removal_is_allowed(self):
        """Removing exactly the available quantity (resulting in 0) must succeed."""
        updated_product = {**SAMPLE_PRODUCT, "quantity_on_hand": 0}
        with (
            patch(
                "app.modules.inventory.service.repository.get_product_by_id",
                new_callable=AsyncMock,
                return_value=self._existing_product(quantity=10),
            ),
            patch(
                "app.modules.inventory.service.repository.update_product",
                new_callable=AsyncMock,
                return_value=updated_product,
            ),
            patch(
                "app.modules.inventory.service.repository.create_stock_adjustment",
                new_callable=AsyncMock,
                return_value={**SAMPLE_ADJUSTMENT, "adjustment_type": "REMOVE", "quantity_delta": 10},
            ),
        ):
            response = client.post(
                f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}/stock-adjustments",
                json={
                    "adjustment_type": "REMOVE",
                    "quantity_delta": 10,
                    "reason": "Full clearance",
                },
                headers=AUTH_HEADER,
            )
        assert response.status_code == 201

    def test_add_adjustment_always_succeeds(self):
        """ADD adjustments must always succeed regardless of current stock."""
        with (
            patch(
                "app.modules.inventory.service.repository.get_product_by_id",
                new_callable=AsyncMock,
                return_value=self._existing_product(quantity=0),
            ),
            patch(
                "app.modules.inventory.service.repository.update_product",
                new_callable=AsyncMock,
                return_value={**SAMPLE_PRODUCT, "quantity_on_hand": 20},
            ),
            patch(
                "app.modules.inventory.service.repository.create_stock_adjustment",
                new_callable=AsyncMock,
                return_value=SAMPLE_ADJUSTMENT,
            ),
        ):
            response = client.post(
                f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}/stock-adjustments",
                json={
                    "adjustment_type": "ADD",
                    "quantity_delta": 20,
                    "reason": "New delivery",
                },
                headers=AUTH_HEADER,
            )
        assert response.status_code == 201

    def test_adjustment_on_nonexistent_product_returns_404(self):
        """Adjustments against a non-existent product must return 404."""
        with patch(
            "app.modules.inventory.service.repository.get_product_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.post(
                "/api/v1/inventory/products/nonexistent_prod/stock-adjustments",
                json={
                    "adjustment_type": "ADD",
                    "quantity_delta": 5,
                    "reason": "Ghost product",
                },
                headers=AUTH_HEADER,
            )
        assert response.status_code == 404
        assert_error_shape(response.json())

    def test_invalid_adjustment_type_returns_400(self):
        """An unrecognised adjustment_type must fail Pydantic validation."""
        response = client.post(
            f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}/stock-adjustments",
            json={
                "adjustment_type": "TELEPORT",
                "quantity_delta": 5,
                "reason": "Test",
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Test Class 3: Update (patch) product
# ---------------------------------------------------------------------------

class TestUpdateProduct:
    """PATCH /api/v1/inventory/products/{product_id} – partial product updates."""

    def test_patch_product_returns_200(self):
        """A valid patch request must return 200 OK."""
        updated = {**SAMPLE_PRODUCT, "name": "Updated Widget", "price": 19.99}
        with (
            patch(
                "app.modules.inventory.service.repository.get_product_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_PRODUCT,
            ),
            patch(
                "app.modules.inventory.service.repository.update_product",
                new_callable=AsyncMock,
                return_value=updated,
            ),
        ):
            response = client.patch(
                f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}",
                json={"name": "Updated Widget", "price": 19.99},
                headers=AUTH_HEADER,
            )
        assert response.status_code == 200

    def test_patch_product_response_contains_request_id(self):
        """Response envelope must contain request_id after a patch."""
        updated = {**SAMPLE_PRODUCT, "name": "Updated Widget"}
        with (
            patch(
                "app.modules.inventory.service.repository.get_product_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_PRODUCT,
            ),
            patch(
                "app.modules.inventory.service.repository.update_product",
                new_callable=AsyncMock,
                return_value=updated,
            ),
        ):
            response = client.patch(
                f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}",
                json={"name": "Updated Widget"},
                headers=AUTH_HEADER,
            )
        assert "request_id" in response.json()

    def test_patch_product_updates_name(self):
        """Patched name must appear in the response."""
        updated = {**SAMPLE_PRODUCT, "name": "Renamed Widget"}
        with (
            patch(
                "app.modules.inventory.service.repository.get_product_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_PRODUCT,
            ),
            patch(
                "app.modules.inventory.service.repository.update_product",
                new_callable=AsyncMock,
                return_value=updated,
            ),
        ):
            response = client.patch(
                f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}",
                json={"name": "Renamed Widget"},
                headers=AUTH_HEADER,
            )
        assert response.json()["product"]["name"] == "Renamed Widget"

    def test_patch_nonexistent_product_returns_404(self):
        """Patching a product that doesn't exist must return 404."""
        with patch(
            "app.modules.inventory.service.repository.get_product_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.patch(
                "/api/v1/inventory/products/ghost_prod",
                json={"name": "Ghost"},
                headers=AUTH_HEADER,
            )
        assert response.status_code == 404
        assert_error_shape(response.json())

    def test_patch_product_requires_auth(self):
        """PATCH without token must return 401."""
        response = client.patch(
            f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}",
            json={"name": "No Auth Widget"},
        )
        assert response.status_code == 401

    def test_patch_with_invalid_status_returns_400(self):
        """An unrecognised status value must fail Pydantic validation."""
        response = client.patch(
            f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}",
            json={"status": "DELETED"},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 400

    def test_patch_product_deactivate(self):
        """Setting status=INACTIVE must succeed."""
        updated = {**SAMPLE_PRODUCT, "status": "INACTIVE"}
        with (
            patch(
                "app.modules.inventory.service.repository.get_product_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_PRODUCT,
            ),
            patch(
                "app.modules.inventory.service.repository.update_product",
                new_callable=AsyncMock,
                return_value=updated,
            ),
        ):
            response = client.patch(
                f"/api/v1/inventory/products/{FAKE_PRODUCT_ID}",
                json={"status": "INACTIVE"},
                headers=AUTH_HEADER,
            )
        assert response.status_code == 200
        assert response.json()["product"]["status"] == "INACTIVE"
