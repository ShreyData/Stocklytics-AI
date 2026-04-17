"""
Customer Module router.

Owned by: Customer Module developer.
Base path: /api/v1/customers
"""

from fastapi import APIRouter, Depends

from app.common.auth import AuthenticatedUser, require_auth
from app.common.exceptions import ForbiddenError
from app.common.responses import success_response
from app.modules.customer.schemas import CustomerCreateRequest
from app.modules.customer.service import CustomerService

router = APIRouter()
customer_service = CustomerService()

@router.post("", status_code=201)
async def create_customer(
    req: CustomerCreateRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    if req.store_id != user.store_id:
        req.store_id = user.store_id  # Force the auth token's store_id
        
    customer = await customer_service.create_customer(req)
    return success_response({"customer": customer}, status_code=201)

@router.get("", status_code=200)
async def list_customers(
    user: AuthenticatedUser = Depends(require_auth),
):
    items = await customer_service.list_customers(user.store_id)
    return success_response({"items": items}, status_code=200)

@router.get("/{customer_id}", status_code=200)
async def get_customer(
    customer_id: str,
    user: AuthenticatedUser = Depends(require_auth),
):
    customer = await customer_service.get_customer(user.store_id, customer_id)
    return success_response({"customer": customer}, status_code=200)

@router.get("/{customer_id}/purchase-history", status_code=200)
async def get_purchase_history(
    customer_id: str,
    user: AuthenticatedUser = Depends(require_auth),
):
    history = await customer_service.get_purchase_history(user.store_id, customer_id)
    return success_response({
        "customer_id": customer_id,
        "transactions": history
    }, status_code=200)
