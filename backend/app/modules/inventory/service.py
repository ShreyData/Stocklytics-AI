"""
Inventory Module – Service layer.

Contains all business logic for inventory management.
Routes are thin; all domain decisions live here.

Business rules enforced here:
    1. Inventory is the single source of truth for stock.
    2. Stock must NEVER go negative.
    3. Every product record must carry a store_id.
    4. Expiry status is always computed, never stored externally.
    5. Every stock change creates an immutable audit record.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from app.common.exceptions import NotFoundError, ValidationError as AppValidationError
from app.modules.inventory import repository
from app.modules.inventory.schemas import (
    EXPIRY_STATUS_EXPIRED,
    EXPIRY_STATUS_EXPIRING_SOON,
    EXPIRY_STATUS_OK,
    ADJUSTMENT_TYPE_REMOVE,
    ADJUSTMENT_TYPE_SALE_DEDUCTION,
    ProductCreateRequest,
    ProductUpdateRequest,
    StockAdjustmentRequest,
)

logger = logging.getLogger(__name__)

# Number of days ahead within which a product is considered "expiring soon"
EXPIRING_SOON_DAYS = 7


# ---------------------------------------------------------------------------
# Expiry helpers
# ---------------------------------------------------------------------------

def compute_expiry_status(expiry_date: Optional[datetime]) -> str:
    """
    Compute the expiry_status field value from an expiry_date.

    Rules:
        EXPIRED       → expiry_date < today (UTC)
        EXPIRING_SOON → expiry_date within the next EXPIRING_SOON_DAYS days
        OK            → everything else (including None)
    """
    if expiry_date is None:
        return EXPIRY_STATUS_OK

    now_utc = datetime.now(timezone.utc)

    # Normalise to timezone-aware for safe comparison
    if expiry_date.tzinfo is None:
        expiry_date = expiry_date.replace(tzinfo=timezone.utc)

    if expiry_date < now_utc:
        return EXPIRY_STATUS_EXPIRED

    if expiry_date <= now_utc + timedelta(days=EXPIRING_SOON_DAYS):
        return EXPIRY_STATUS_EXPIRING_SOON

    return EXPIRY_STATUS_OK


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _firestore_to_response(data: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a Firestore document dict to a JSON-serialisable response dict.

    Firestore timestamps are google.cloud.firestore.DatetimeWithNanoseconds
    objects; we normalise them to ISO-8601 strings.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            # Ensure timezone-aware before calling isoformat
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Product service functions
# ---------------------------------------------------------------------------

async def create_product(
    payload: ProductCreateRequest,
    store_id: str,
) -> dict[str, Any]:
    """
    Create a new product record.

    Steps:
        1. Compute expiry_status from expiry_date.
        2. Build the Firestore document.
        3. Persist and return the serialised product.
    """
    product_id = f"prod_{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)

    expiry_status = compute_expiry_status(payload.expiry_date)

    document: dict[str, Any] = {
        "product_id": product_id,
        "store_id": store_id,
        "name": payload.name,
        "category": payload.category,
        "price": payload.price,
        "quantity_on_hand": payload.quantity_on_hand,
        "reorder_threshold": payload.reorder_threshold,
        "expiry_date": payload.expiry_date,
        "expiry_status": expiry_status,
        "status": payload.status,
        "created_at": now,
        "updated_at": now,
    }

    stored = await repository.create_product(product_id, document)
    return _firestore_to_response(stored)


async def list_products(
    store_id: str,
    low_stock_only: bool = False,
    expiry_before: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """
    Retrieve products for a store with optional filters.

    Args:
        store_id:      The store to filter by.
        low_stock_only: Only return products at or below their reorder threshold.
        expiry_before: Only return products whose expiry_date is before this value.
    """
    products = await repository.list_products(
        store_id=store_id,
        low_stock_only=low_stock_only,
        expiry_before=expiry_before,
    )
    return [_firestore_to_response(p) for p in products]


async def get_product(product_id: str, store_id: str) -> dict[str, Any]:
    """
    Fetch a single product by ID, scoped to the caller's store.

    Raises NotFoundError if the product does not exist or belongs to
    a different store (prevents cross-store data leakage).
    """
    product = await repository.get_product_by_id(product_id)
    if product is None or product.get("store_id") != store_id:
        raise NotFoundError(
            f"Product '{product_id}' not found.",
            details={"product_id": product_id},
        )
    return _firestore_to_response(product)


async def update_product(
    product_id: str,
    payload: ProductUpdateRequest,
    store_id: str,
) -> dict[str, Any]:
    """
    Apply a partial update to a product.

    Steps:
        1. Verify the product exists and belongs to this store.
        2. Build the update dict from provided (non-None) fields.
        3. Recompute expiry_status if relevant fields changed.
        4. Persist and return the updated product.
    """
    existing = await repository.get_product_by_id(product_id)
    if existing is None or existing.get("store_id") != store_id:
        raise NotFoundError(
            f"Product '{product_id}' not found.",
            details={"product_id": product_id},
        )

    updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}

    if payload.name is not None:
        updates["name"] = payload.name
    if payload.category is not None:
        updates["category"] = payload.category
    if payload.price is not None:
        updates["price"] = payload.price
    if payload.reorder_threshold is not None:
        updates["reorder_threshold"] = payload.reorder_threshold
    if payload.status is not None:
        updates["status"] = payload.status

    # Recompute expiry_status when expiry_date is explicitly sent
    if "expiry_date" in payload.model_fields_set:
        updates["expiry_date"] = payload.expiry_date
        updates["expiry_status"] = compute_expiry_status(payload.expiry_date)
    else:
        # Recompute against the existing expiry_date to handle date-of-day drift
        existing_expiry = existing.get("expiry_date")
        if isinstance(existing_expiry, datetime):
            updates["expiry_status"] = compute_expiry_status(existing_expiry)

    updated = await repository.update_product(product_id, updates)
    if updated is None:
        raise NotFoundError(
            f"Product '{product_id}' not found.",
            details={"product_id": product_id},
        )
    return _firestore_to_response(updated)


# ---------------------------------------------------------------------------
# Stock adjustment service function
# ---------------------------------------------------------------------------

async def apply_stock_adjustment(
    product_id: str,
    payload: StockAdjustmentRequest,
    store_id: str,
    user_id: str,
) -> dict[str, Any]:
    """
    Apply a stock adjustment to a product.

    Steps:
        1. Fetch the product – raise 404 if not found.
        2. Calculate the signed quantity delta.
        3. Reject if the resulting quantity would go negative.
        4. Update quantity_on_hand on the product document.
        5. Insert an immutable stock_adjustments audit record.
        6. Return the adjustment record.

    Business rule: REMOVE and SALE_DEDUCTION decrease stock; ADD increases it.
    MANUAL_CORRECTION can go either way but is always stored as a positive
    quantity_delta; the caller signals direction via adjustment_type.
    """
    product = await repository.get_product_by_id(product_id)
    if product is None or product.get("store_id") != store_id:
        raise NotFoundError(
            f"Product '{product_id}' not found.",
            details={"product_id": product_id},
        )

    current_quantity: int = product.get("quantity_on_hand", 0)
    delta = payload.quantity_delta

    # Determine whether this adjustment adds or subtracts stock
    is_subtraction = payload.adjustment_type in {
        ADJUSTMENT_TYPE_REMOVE,
        ADJUSTMENT_TYPE_SALE_DEDUCTION,
    }

    if is_subtraction:
        new_quantity = current_quantity - delta
    else:
        new_quantity = current_quantity + delta

    # Business rule: stock must NEVER go negative
    if new_quantity < 0:
        raise AppValidationError(
            "Stock adjustment would result in negative stock, which is not allowed.",
            details={
                "current_quantity": current_quantity,
                "requested_delta": delta,
                "adjustment_type": payload.adjustment_type,
                "resulting_quantity": new_quantity,
            },
        )

    now = datetime.now(timezone.utc)

    # Persist the updated stock level
    await repository.update_product(
        product_id,
        {
            "quantity_on_hand": new_quantity,
            "updated_at": now,
        },
    )

    # Create the immutable audit record
    adjustment_id = f"adj_{uuid.uuid4().hex}"
    adjustment_doc: dict[str, Any] = {
        "adjustment_id": adjustment_id,
        "store_id": store_id,
        "product_id": product_id,
        "adjustment_type": payload.adjustment_type,
        "quantity_delta": delta,
        "reason": payload.reason,
        "source_ref": payload.source_ref,
        "created_by": user_id,
        "created_at": now,
    }

    stored_adjustment = await repository.create_stock_adjustment(
        adjustment_id, adjustment_doc
    )

    logger.info(
        "Stock adjustment applied",
        extra={
            "product_id": product_id,
            "adjustment_type": payload.adjustment_type,
            "delta": delta,
            "old_quantity": current_quantity,
            "new_quantity": new_quantity,
        },
    )

    return _firestore_to_response(stored_adjustment)
