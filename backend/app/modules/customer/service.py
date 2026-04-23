import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.common.exceptions import ConflictError, NotFoundError
from app.modules.customer.repository import CustomerRepository
from app.modules.customer.schemas import CustomerCreateRequest


class CustomerAlreadyExistsError(ConflictError):
    """Raised when a customer with the same phone already exists in the store."""

    error_code = "CUSTOMER_ALREADY_EXISTS"


class CustomerNotFoundError(NotFoundError):
    """Raised when a customer is not found in the active store scope."""

    error_code = "CUSTOMER_NOT_FOUND"


class CustomerService:
    def __init__(self):
        self.repo = CustomerRepository()

    @staticmethod
    def _to_customer_response(customer: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "customer_id": customer["customer_id"],
            "store_id": customer["store_id"],
            "name": customer["name"],
            "phone": customer["phone"],
            "total_spend": float(customer.get("total_spend", 0.0)),
            "visit_count": int(customer.get("visit_count", 0)),
            "last_purchase_at": customer.get("last_purchase_at"),
        }

    @staticmethod
    def _to_customer_list_item(customer: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "customer_id": customer["customer_id"],
            "name": customer["name"],
            "phone": customer["phone"],
            "total_spend": float(customer.get("total_spend", 0.0)),
            "visit_count": int(customer.get("visit_count", 0)),
            "last_purchase_at": customer.get("last_purchase_at"),
        }

    async def create_customer(self, req: CustomerCreateRequest) -> Dict[str, Any]:
        # Enforce unique phone per store
        existing_customer = await self.repo.get_customer_by_phone(req.store_id, req.phone)
        if existing_customer:
            raise CustomerAlreadyExistsError(
                "Customer with this phone already exists.",
                details={"phone": req.phone, "message": f"Customer with phone {req.phone} already exists."}
            )

        customer_id = f"cust_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)

        customer_data = {
            "store_id": req.store_id,
            "name": req.name,
            "phone": req.phone,
            "total_spend": 0.0,
            "visit_count": 0,
            "last_purchase_at": None,
            "created_at": now,
            "updated_at": now,
        }

        # Store in Firestore
        created = await self.repo.create_customer(customer_id, customer_data)
        return self._to_customer_response(created)

    async def list_customers(self, store_id: str) -> List[Dict[str, Any]]:
        customers = await self.repo.list_customers(store_id)
        return [self._to_customer_list_item(customer) for customer in customers]

    async def get_customer(self, store_id: str, customer_id: str) -> Dict[str, Any]:
        customer = await self.repo.get_customer_by_id(customer_id)
        if not customer or customer.get("store_id") != store_id:
            raise CustomerNotFoundError(
                "Customer not found in this store.",
                details={"customer_id": customer_id}
            )
        return self._to_customer_response(customer)

    async def get_purchase_history(self, store_id: str, customer_id: str) -> List[Dict[str, Any]]:
        # Ensure customer exists first
        await self.get_customer(store_id, customer_id)
        
        history = await self.repo.get_purchase_history(store_id, customer_id)
        return history
