import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.common.exceptions import ConflictError, NotFoundError
from app.modules.customer.repository import CustomerRepository
from app.modules.customer.schemas import CustomerCreateRequest


class CustomerService:
    def __init__(self):
        self.repo = CustomerRepository()

    async def create_customer(self, req: CustomerCreateRequest) -> Dict[str, Any]:
        # Enforce unique phone per store
        existing_customer = await self.repo.get_customer_by_phone(req.store_id, req.phone)
        if existing_customer:
            raise ConflictError(
                "CUSTOMER_ALREADY_EXISTS",
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
        return created

    async def list_customers(self, store_id: str) -> List[Dict[str, Any]]:
        return await self.repo.list_customers(store_id)

    async def get_customer(self, store_id: str, customer_id: str) -> Dict[str, Any]:
        customer = await self.repo.get_customer_by_id(customer_id)
        if not customer or customer.get("store_id") != store_id:
            raise NotFoundError(
                "CUSTOMER_NOT_FOUND",
                details={"customer_id": customer_id}
            )
        return customer

    async def get_purchase_history(self, store_id: str, customer_id: str) -> List[Dict[str, Any]]:
        # Ensure customer exists first
        await self.get_customer(store_id, customer_id)
        
        history = await self.repo.get_purchase_history(store_id, customer_id)
        return history
