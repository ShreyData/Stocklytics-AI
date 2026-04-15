"""
Billing Module – Pydantic schemas.

All JSON fields use snake_case per project conventions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRANSACTION_STATUS_COMPLETED = "COMPLETED"
TRANSACTION_STATUS_FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class LineItemRequest(BaseModel):
    """A single product line in a billing transaction."""

    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1, description="Number of units sold. Must be ≥ 1.")
    unit_price: float = Field(..., ge=0, description="Price per unit at time of sale.")


class LineItemResponse(BaseModel):
    """Line item as stored in the transaction record."""

    product_id: str
    quantity: int
    unit_price: float
    line_total: float


# ---------------------------------------------------------------------------
# Transaction schemas
# ---------------------------------------------------------------------------

class TransactionCreateRequest(BaseModel):
    """
    Payload for POST /api/v1/billing/transactions.

    idempotency_key is mandatory.  Callers should generate a unique key per
    logical billing attempt (e.g. UUIDv4) and retry using the same key if a
    network error occurs.
    """

    idempotency_key: str = Field(..., min_length=1, max_length=256)
    items: list[LineItemRequest] = Field(..., min_length=1)
    notes: Optional[str] = Field(default=None, max_length=1000)


class TransactionResponse(BaseModel):
    """Full transaction record returned from the API."""

    transaction_id: str
    store_id: str
    idempotency_key: str
    items: list[LineItemResponse]
    total_amount: float
    status: str
    notes: Optional[str]
    created_by: str
    created_at: datetime
