import pytest
from unittest.mock import AsyncMock, patch

from app.modules.alerts.engine import evaluate_low_stock
from app.modules.alerts.schemas import ALERT_STATUS_ACTIVE


@pytest.fixture
def mock_repository():
    with patch("app.modules.alerts.engine.repository") as mock_repo:
        # Provide default async mocks
        mock_repo.get_alert_by_condition = AsyncMock(return_value=None)
        mock_repo.create_alert = AsyncMock()
        mock_repo.update_alert = AsyncMock()
        mock_repo.write_alert_event = AsyncMock()
        yield mock_repo


@pytest.fixture
def mock_resolve_alert():
    with patch("app.modules.alerts.engine.resolve_alert") as mock_resolve:
        yield mock_resolve


@pytest.mark.asyncio
async def test_evaluate_low_stock_creates_alert(mock_repository):
    """Test that a LOW_STOCK alert is created when stock <= threshold."""
    await evaluate_low_stock(
        store_id="store_1",
        product_id="prod_1",
        product_name="Test Product",
        current_stock=5,
        reorder_threshold=10
    )
    
    mock_repository.get_alert_by_condition.assert_called_once_with("store_1", "LOW_STOCK_prod_1")
    mock_repository.create_alert.assert_called_once()
    
    # Verify created alert data
    created_id, created_data = mock_repository.create_alert.call_args[0]
    assert created_data["alert_type"] == "LOW_STOCK"
    assert created_data["status"] == ALERT_STATUS_ACTIVE
    assert created_data["severity"] == "HIGH"
    assert created_data["metadata"]["quantity_on_hand"] == 5
    assert created_data["metadata"]["reorder_threshold"] == 10
    
    mock_repository.write_alert_event.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_low_stock_critical_severity(mock_repository):
    """Test that severity is CRITICAL when stock is 0."""
    await evaluate_low_stock(
        store_id="store_1",
        product_id="prod_1",
        product_name="Test Product",
        current_stock=0,
        reorder_threshold=10
    )
    
    created_id, created_data = mock_repository.create_alert.call_args[0]
    assert created_data["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_evaluate_low_stock_resolves_existing(mock_repository, mock_resolve_alert):
    """Test that an existing alert is resolved when stock goes above threshold."""
    mock_repository.get_alert_by_condition.return_value = {
        "alert_id": "existing_alert_1",
        "store_id": "store_1",
        "condition_key": "LOW_STOCK_prod_1"
    }
    
    await evaluate_low_stock(
        store_id="store_1",
        product_id="prod_1",
        product_name="Test Product",
        current_stock=15,
        reorder_threshold=10
    )
    
    # Should attempt to resolve it
    mock_resolve_alert.assert_called_once_with(
        alert_id="existing_alert_1",
        store_id="store_1",
        user_id="system",
        resolution_note="Condition automatically cleared."
    )
    mock_repository.create_alert.assert_not_called()
    mock_repository.update_alert.assert_not_called()
