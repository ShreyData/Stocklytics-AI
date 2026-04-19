"""
Inventory Module – FastAPI route handlers.

Base path (registered in main.py): /api/v1/inventory

Endpoints:
    POST   /products                               – create a product
    GET    /products                               – list products (filterable)
    GET    /products/{product_id}                  – get a single product
    PATCH  /products/{product_id}                  – update product fields
    POST   /products/{product_id}/stock-adjustments – record a stock change

Route handlers are intentionally thin: they validate input via Pydantic,
delegate to the service layer, and return structured responses.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.common.auth import AuthenticatedUser, require_auth
from app.common.responses import success_response
from app.modules.inventory import service
from app.modules.inventory.schemas import (
    ProductCreateRequest,
    ProductUpdateRequest,
    StockAdjustmentRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/v1/inventory/products
# ---------------------------------------------------------------------------

@router.post("/products", status_code=201)
async def create_product(
    payload: ProductCreateRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Create a new product in the caller's store."""
    product = await service.create_product(payload=payload, store_id=user.store_id)
    return success_response({"product": product}, status_code=201)


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/products
# ---------------------------------------------------------------------------

@router.get("/products", status_code=200)
async def list_products(
    store_id: Optional[str] = Query(default=None, description="Store scope. Must match authenticated store_id when provided."),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum items to return in one response."),
    page_token: Optional[str] = Query(default=None, description="Opaque pagination token from previous response."),
    low_stock_only: bool = Query(default=False, description="Only return products at or below reorder threshold."),
    expiry_before: Optional[datetime] = Query(default=None, description="Only return products expiring before this ISO-8601 datetime."),
    user: AuthenticatedUser = Depends(require_auth),
):
    """
    List all products for the caller's store.

    Supports optional query filters:
        - low_stock_only=true
        - expiry_before=<ISO-8601 datetime>
    """
    products = await service.list_products(
        store_id=user.store_id,
        requested_store_id=store_id,
        limit=limit,
        page_token=page_token,
        low_stock_only=low_stock_only,
        expiry_before=expiry_before,
    )
    return success_response(products)


# ---------------------------------------------------------------------------
# GET /api/v1/inventory/products/{product_id}
# ---------------------------------------------------------------------------

@router.get("/products/{product_id}", status_code=200)
async def get_product(
    product_id: str,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Retrieve a single product by ID, scoped to the caller's store."""
    product = await service.get_product(
        product_id=product_id, store_id=user.store_id
    )
    return success_response({"product": product})


# ---------------------------------------------------------------------------
# PATCH /api/v1/inventory/products/{product_id}
# ---------------------------------------------------------------------------

@router.patch("/products/{product_id}", status_code=200)
async def update_product(
    product_id: str,
    payload: ProductUpdateRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """Partially update a product. Only provided fields are modified."""
    product = await service.update_product(
        product_id=product_id,
        payload=payload,
        store_id=user.store_id,
    )
    return success_response({"product": product})


# ---------------------------------------------------------------------------
# POST /api/v1/inventory/products/{product_id}/stock-adjustments
# ---------------------------------------------------------------------------

@router.post("/products/{product_id}/stock-adjustments", status_code=200)
async def create_stock_adjustment(
    product_id: str,
    payload: StockAdjustmentRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """
    Record a stock adjustment for a product.

    Validates that the resulting quantity never drops below zero.
    Creates an immutable audit record in stock_adjustments.
    """
    result = await service.apply_stock_adjustment(
        product_id=product_id,
        payload=payload,
        store_id=user.store_id,
        user_id=user.user_id,
    )
    return success_response(result, status_code=200)
