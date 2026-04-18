import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

# Standard testing auth header (gives store_id="store_001" and role="admin" via stub)
AUTH_HEADER = {"Authorization": "Bearer dev-token"}


@pytest.fixture
def mock_repo():
    """Mock the CustomerRepository so we don't hit Firestore."""
    from app.modules.customer.router import customer_service
    
    with patch.object(customer_service, 'repo') as mock_repo_instance:
        # Replace async methods with AsyncMock
        mock_repo_instance.get_customer_by_phone = AsyncMock()
        mock_repo_instance.create_customer = AsyncMock()
        mock_repo_instance.get_customer_by_id = AsyncMock()
        mock_repo_instance.get_purchase_history = AsyncMock()
        
        yield mock_repo_instance


class TestCustomerAPI:
    
    # -----------------------------------------------------------------------
    # A) HAPPY PATHS
    # -----------------------------------------------------------------------
    
    def test_create_customer_success(self, mock_repo):
        """POST /customers -> successfully creates a customer"""
        mock_repo.get_customer_by_phone.return_value = None
        mock_repo.create_customer.return_value = {
            "customer_id": "cust_123",
            "store_id": "store_001",
            "name": "Jane Doe",
            "phone": "555-0100",
            "total_spend": 0.0,
            "visit_count": 0,
            "last_purchase_at": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        
        response = client.post(
            "/api/v1/customers",
            headers=AUTH_HEADER,
            json={
                "store_id": "store_001",
                "name": "Jane Doe",
                "phone": "555-0100"
            }
        )
        
        assert response.status_code == 201
        body = response.json()
        assert "customer" in body
        assert body["customer"]["customer_id"] == "cust_123"
        assert body["customer"]["name"] == "Jane Doe"
        # Validate that repository methods were called
        mock_repo.get_customer_by_phone.assert_called_once_with("store_001", "555-0100")
        mock_repo.create_customer.assert_called_once()

    def test_get_customer_success(self, mock_repo):
        """GET /customers/{customer_id} -> returns correct customer"""
        mock_repo.get_customer_by_id.return_value = {
            "customer_id": "cust_123",
            "store_id": "store_001",
            "name": "Jane Doe",
            "phone": "555-0100",
            "total_spend": 120.50,
            "visit_count": 2,
            "last_purchase_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        
        response = client.get(
            "/api/v1/customers/cust_123",
            headers=AUTH_HEADER
        )
        
        assert response.status_code == 200
        body = response.json()
        assert "customer" in body
        assert body["customer"]["customer_id"] == "cust_123"
        assert body["customer"]["total_spend"] == 120.50

    def test_get_purchase_history_contract_enforced(self, mock_repo):
        """GET /customers/{customer_id}/purchase-history -> exact contract mapped"""
        # Service checks customer exists first
        mock_repo.get_customer_by_id.return_value = {
            "customer_id": "cust_123",
            "store_id": "store_001"
        }
        
        sale_ts = datetime.now(timezone.utc)
        mock_repo.get_purchase_history.return_value = [
            {
                "transaction_id": "tx_abc123",
                "total_amount": 99.99,
                "sale_timestamp": sale_ts
            }
        ]
        
        response = client.get(
            "/api/v1/customers/cust_123/purchase-history",
            headers=AUTH_HEADER
        )
        
        assert response.status_code == 200
        body = response.json()
        
        assert body["customer_id"] == "cust_123"
        transactions = body["transactions"]
        assert len(transactions) == 1
        
        tx = transactions[0]
        # Assert strictly only these 3 keys exist in the response item
        assert set(tx.keys()) == {"transaction_id", "total_amount", "sale_timestamp"}
        assert tx["transaction_id"] == "tx_abc123"
        assert tx["total_amount"] == 99.99
        
        # Validate timestamp format (ISO string)
        # Fast API / Pydantic emits datetime as ISO 8601 strings
        dt_str = tx["sale_timestamp"].replace("Z", "+00:00")
        assert datetime.fromisoformat(dt_str) is not None

    # -----------------------------------------------------------------------
    # B) KEY FAILURE CASES
    # -----------------------------------------------------------------------
    
    def test_create_customer_duplicate_phone(self, mock_repo):
        """Duplicate phone number -> 409 Conflict"""
        mock_repo.get_customer_by_phone.return_value = {
            "customer_id": "cust_old",
            "store_id": "store_001",
            "phone": "555-0100"
        }
        
        response = client.post(
            "/api/v1/customers",
            headers=AUTH_HEADER,
            json={
                "store_id": "store_001",
                "name": "Jane Variant",
                "phone": "555-0100"
            }
        )
        
        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "CONFLICT"

    def test_create_customer_store_scope_violation(self, mock_repo):
        """Token store_id != request.store_id -> 403 Forbidden"""
        response = client.post(
            "/api/v1/customers",
            headers=AUTH_HEADER,
            json={
                "store_id": "store_999",  # Conflicts with token's 'store_001'
                "name": "Jane Doe",
                "phone": "555-0100"
            }
        )
        
        assert response.status_code == 403
        body = response.json()
        assert body["error"]["code"] == "FORBIDDEN"

    def test_get_customer_not_found(self, mock_repo):
        """Customer not found -> 404"""
        mock_repo.get_customer_by_id.return_value = None
        
        response = client.get(
            "/api/v1/customers/cust_invalid",
            headers=AUTH_HEADER
        )
        
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "NOT_FOUND"

    def test_get_customer_scope_violation(self, mock_repo):
        """Customer belongs to a different store -> 404 Not Found (privacy)"""
        mock_repo.get_customer_by_id.return_value = {
            "customer_id": "cust_123",
            "store_id": "store_999",  # Cross-store access denied
            "name": "Jane Doe"
        }
        
        response = client.get(
            "/api/v1/customers/cust_123",
            headers=AUTH_HEADER
        )
        
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
