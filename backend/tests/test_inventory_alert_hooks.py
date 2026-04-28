from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.inventory import service
from app.modules.inventory.schemas import (
    ProductCreateRequest,
    ProductUpdateRequest,
    StockAdjustmentRequest,
)


@pytest.mark.asyncio
async def test_create_product_evaluates_low_stock_and_expiry_alerts():
    payload = ProductCreateRequest(
        store_id="store_001",
        name="Milk 500ml",
        category="Dairy",
        price=28.0,
        quantity=3,
        reorder_threshold=5,
        expiry_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
        status="ACTIVE",
    )

    with (
        patch(
            "app.modules.inventory.service.repository.create_product",
            new_callable=AsyncMock,
            return_value={
                "product_id": "prod_123",
                "store_id": "store_001",
                "name": payload.name,
                "category": payload.category,
                "price": payload.price,
                "quantity_on_hand": payload.quantity,
                "reorder_threshold": payload.reorder_threshold,
                "expiry_date": payload.expiry_date,
                "status": payload.status,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        ),
        patch("app.modules.inventory.service._should_skip_alert_hooks", return_value=False),
        patch("app.modules.inventory.service.evaluate_low_stock", new_callable=AsyncMock) as low_stock_mock,
        patch("app.modules.inventory.service.evaluate_expiry_soon", new_callable=AsyncMock) as expiry_mock,
    ):
        await service.create_product(payload=payload, store_id="store_001")

    low_stock_mock.assert_awaited_once()
    expiry_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_product_evaluates_low_stock_and_expiry_alerts():
    existing = {
        "product_id": "prod_123",
        "store_id": "store_001",
        "name": "Butter Biscuit",
        "category": "Snacks",
        "price": 35.0,
        "quantity_on_hand": 4,
        "reorder_threshold": 8,
        "expiry_date": datetime(2026, 5, 2, tzinfo=timezone.utc),
        "status": "ACTIVE",
    }
    updated = {**existing, "reorder_threshold": 6, "updated_at": datetime.now(timezone.utc)}
    payload = ProductUpdateRequest(store_id="store_001", reorder_threshold=6)

    with (
        patch("app.modules.inventory.service.repository.get_product_by_id", new_callable=AsyncMock, return_value=existing),
        patch("app.modules.inventory.service.repository.update_product", new_callable=AsyncMock, return_value=updated),
        patch("app.modules.inventory.service._should_skip_alert_hooks", return_value=False),
        patch("app.modules.inventory.service.evaluate_low_stock", new_callable=AsyncMock) as low_stock_mock,
        patch("app.modules.inventory.service.evaluate_expiry_soon", new_callable=AsyncMock) as expiry_mock,
    ):
        await service.update_product(product_id="prod_123", payload=payload, store_id="store_001")

    low_stock_mock.assert_awaited_once()
    expiry_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_stock_adjustment_evaluates_low_stock_and_expiry_alerts():
    payload = StockAdjustmentRequest(
        store_id="store_001",
        adjustment_type="REMOVE",
        quantity_delta=2,
        reason="Damaged stock",
    )
    product = {
        "product_id": "prod_123",
        "store_id": "store_001",
        "name": "Yogurt Cup",
        "quantity_on_hand": 1,
        "reorder_threshold": 3,
        "expiry_date": datetime(2026, 4, 29, tzinfo=timezone.utc),
        "status": "ACTIVE",
    }

    with (
        patch(
            "app.modules.inventory.service.repository.apply_stock_adjustment_atomic",
            new_callable=AsyncMock,
            return_value=(datetime.now(timezone.utc), 1),
        ),
        patch("app.modules.inventory.service.repository.get_product_by_id", new_callable=AsyncMock, return_value=product),
        patch("app.modules.inventory.service._should_skip_alert_hooks", return_value=False),
        patch("app.modules.inventory.service.evaluate_low_stock", new_callable=AsyncMock) as low_stock_mock,
        patch("app.modules.inventory.service.evaluate_expiry_soon", new_callable=AsyncMock) as expiry_mock,
    ):
        await service.apply_stock_adjustment(
            product_id="prod_123",
            payload=payload,
            store_id="store_001",
            user_id="user_001",
        )

    low_stock_mock.assert_awaited_once()
    expiry_mock.assert_awaited_once()
