"""
Inventory Module – Pydantic schemas.

Defines request/response models for all inventory endpoints.
All field names are snake_case per project naming conventions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations (plain string constants – avoids Pydantic enum serialisation edge-cases)
# ---------------------------------------------------------------------------

EXPIRY_STATUS_OK = "OK"
EXPIRY_STATUS_EXPIRING_SOON = "EXPIRING_SOON"
EXPIRY_STATUS_EXPIRED = "EXPIRED"

PRODUCT_STATUS_ACTIVE = "ACTIVE"
PRODUCT_STATUS_INACTIVE = "INACTIVE"

ADJUSTMENT_TYPE_ADD = "ADD"
ADJUSTMENT_TYPE_REMOVE = "REMOVE"
ADJUSTMENT_TYPE_SALE_DEDUCTION = "SALE_DEDUCTION"
ADJUSTMENT_TYPE_MANUAL_CORRECTION = "MANUAL_CORRECTION"

VALID_ADJUSTMENT_TYPES = {
    ADJUSTMENT_TYPE_ADD,
    ADJUSTMENT_TYPE_REMOVE,
    ADJUSTMENT_TYPE_SALE_DEDUCTION,
    ADJUSTMENT_TYPE_MANUAL_CORRECTION,
}

VALID_PRODUCT_STATUSES = {PRODUCT_STATUS_ACTIVE, PRODUCT_STATUS_INACTIVE}


# ---------------------------------------------------------------------------
# Product schemas
# ---------------------------------------------------------------------------

class ProductCreateRequest(BaseModel):
    """Payload for POST /api/v1/inventory/products."""

    store_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., ge=0)
    quantity: int = Field(..., ge=0)
    reorder_threshold: int = Field(..., ge=0)
    expiry_date: Optional[datetime] = Field(default=None)
    status: str = Field(default=PRODUCT_STATUS_ACTIVE)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_PRODUCT_STATUSES:
            raise ValueError(f"status must be one of {VALID_PRODUCT_STATUSES}")
        return v


class ProductUpdateRequest(BaseModel):
    """Payload for PATCH /api/v1/inventory/products/{product_id}.

    All fields are optional; only provided fields are updated.
    """

    store_id: str = Field(..., min_length=1, max_length=100)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    price: Optional[float] = Field(default=None, ge=0)
    reorder_threshold: Optional[int] = Field(default=None, ge=0)
    expiry_date: Optional[datetime] = Field(default=None)
    status: Optional[str] = Field(default=None)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_PRODUCT_STATUSES:
            raise ValueError(f"status must be one of {VALID_PRODUCT_STATUSES}")
        return v


class ProductResponse(BaseModel):
    """Full product representation returned from the API."""

    product_id: str
    store_id: str
    name: str
    category: str
    price: float
    quantity_on_hand: int
    reorder_threshold: int
    expiry_date: Optional[datetime]
    expiry_status: str
    status: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Stock adjustment schemas
# ---------------------------------------------------------------------------

class StockAdjustmentRequest(BaseModel):
    """Payload for POST /api/v1/inventory/products/{product_id}/stock-adjustments."""

    store_id: str = Field(..., min_length=1, max_length=100)
    adjustment_type: str
    quantity_delta: int = Field(..., ge=1, description="Positive integer representing the magnitude of change.")
    reason: str = Field(..., min_length=1, max_length=500)
    source_ref: Optional[str] = Field(default=None, max_length=200)

    @field_validator("adjustment_type")
    @classmethod
    def validate_adjustment_type(cls, v: str) -> str:
        if v not in VALID_ADJUSTMENT_TYPES:
            raise ValueError(
                f"adjustment_type must be one of {VALID_ADJUSTMENT_TYPES}"
            )
        return v


class StockAdjustmentResponse(BaseModel):
    """Full stock adjustment record returned from the API."""

    adjustment_id: str
    store_id: str
    product_id: str
    adjustment_type: str
    quantity_delta: int
    reason: str
    source_ref: Optional[str]
    created_by: str
    created_at: datetime
