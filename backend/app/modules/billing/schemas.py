"""
Billing Module – Pydantic schemas.

All JSON fields use snake_case per project conventions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


TRANSACTION_STATUS_COMPLETED = "COMPLETED"
TRANSACTION_STATUS_FAILED = "FAILED"

PAYMENT_METHOD_CASH = "cash"
PAYMENT_METHOD_UPI = "upi"
PAYMENT_METHOD_CARD = "card"

VALID_PAYMENT_METHODS = {
    PAYMENT_METHOD_CASH,
    PAYMENT_METHOD_UPI,
    PAYMENT_METHOD_CARD,
}


class LineItemRequest(BaseModel):
    """A single product line in a billing transaction."""

    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1, description="Number of units sold. Must be >= 1.")


class LineItemResponse(BaseModel):
    """Line item returned in billing responses."""

    product_id: str
    quantity: int
    unit_price: float
    line_total: float


class TransactionCreateRequest(BaseModel):
    """Payload for POST /api/v1/billing/transactions."""

    store_id: str = Field(..., min_length=1, max_length=100)
    idempotency_key: str = Field(..., min_length=1, max_length=256)
    customer_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    payment_method: str = Field(..., min_length=1, max_length=20)
    items: list[LineItemRequest] = Field(..., min_length=1)

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, value: str) -> str:
        if value not in VALID_PAYMENT_METHODS:
            raise ValueError(
                f"payment_method must be one of {sorted(VALID_PAYMENT_METHODS)}"
            )
        return value


class TransactionSummaryResponse(BaseModel):
    """Transaction summary used in list responses."""

    transaction_id: str
    customer_id: Optional[str]
    total_amount: float
    sale_timestamp: datetime
    status: str


class TransactionDetailResponse(BaseModel):
    """Detailed transaction payload."""

    transaction_id: str
    store_id: str
    customer_id: Optional[str]
    status: str
    payment_method: str
    total_amount: float
    sale_timestamp: datetime
    items: list[LineItemResponse]
    idempotency_key: Optional[str] = None


class InventoryUpdateResponse(BaseModel):
    """Inventory changes returned after successful billing."""

    product_id: str
    new_quantity_on_hand: int
