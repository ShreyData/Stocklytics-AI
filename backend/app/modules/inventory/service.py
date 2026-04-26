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

from app.common.config import get_settings
from app.common.exceptions import NotFoundError, ValidationError as AppValidationError
from app.modules.alerts.engine import evaluate_low_stock
from app.modules.inventory import repository
from app.modules.inventory.schemas import (
    EXPIRY_STATUS_EXPIRED,
    EXPIRY_STATUS_EXPIRING_SOON,
    EXPIRY_STATUS_OK,
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


def _schedule_low_stock_evaluation(
    *,
    store_id: str,
    product_id: str,
    product_name: str,
    current_stock: int,
    reorder_threshold: int,
) -> None:
    """
    Schedule post-adjustment low-stock evaluation without blocking the response.

    In local mode without Firestore configured, skip the cross-module hook so
    backend tests and bootstrap checks do not accidentally hit live dependencies.
    """
    settings = get_settings()
    if settings.is_local and not settings.firestore_project_id:
        logger.info(
            "Skipping low-stock evaluation in local mode because Firestore is not configured",
            extra={"store_id": store_id, "product_id": product_id},
        )
        return

    import asyncio  # noqa: PLC0415

    async def _run() -> None:
        try:
            await evaluate_low_stock(
                store_id=store_id,
                product_id=product_id,
                product_name=product_name,
                current_stock=current_stock,
                reorder_threshold=reorder_threshold,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Low-stock evaluation failed after stock adjustment",
                extra={"store_id": store_id, "product_id": product_id},
            )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "No running event loop available for low-stock evaluation",
            extra={"store_id": store_id, "product_id": product_id},
        )
        return

    loop.create_task(_run())


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
    _validate_store_scope(payload.store_id, store_id)

    product_id = f"prod_{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)

    expiry_status = compute_expiry_status(payload.expiry_date)

    document: dict[str, Any] = {
        "product_id": product_id,
        "store_id": store_id,
        "name": payload.name,
        "category": payload.category,
        "price": payload.price,
        "quantity_on_hand": payload.quantity,
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
    requested_store_id: Optional[str] = None,
    limit: int = 50,
    page_token: Optional[str] = None,
    low_stock_only: bool = False,
    expiry_before: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Retrieve products for a store with optional filters.

    Args:
        store_id:      The store to filter by.
        low_stock_only: Only return products at or below their reorder threshold.
        expiry_before: Only return products whose expiry_date is before this value.
    """
    _validate_store_scope(requested_store_id, store_id, allow_none=True)

    products = await repository.list_products(
        store_id=store_id,
        low_stock_only=low_stock_only,
        expiry_before=expiry_before,
    )
    start_idx = _parse_page_token(page_token)
    if start_idx >= len(products):
        return {"items": [], "next_page_token": None}

    page = products[start_idx:start_idx + limit]
    next_idx = start_idx + limit
    next_page_token = str(next_idx) if next_idx < len(products) else None
    return {
        "items": [_firestore_to_response(product) for product in page],
        "next_page_token": next_page_token,
    }


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
    _validate_store_scope(payload.store_id, store_id)

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

    Business rule: REMOVE and SALE_DEDUCTION decrease stock.
    ADD and MANUAL_CORRECTION increase stock.
    """
    _validate_store_scope(payload.store_id, store_id)

    delta = payload.quantity_delta
    now = datetime.now(timezone.utc)
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

    try:
        updated_at, new_quantity = await repository.apply_stock_adjustment_atomic(
            product_id=product_id,
            store_id=store_id,
            adjustment_type=payload.adjustment_type,
            quantity_delta=delta,
            adjustment_doc=adjustment_doc,
            updated_at=now,
        )
    except repository.NegativeStockError as exc:
        raise AppValidationError(
            "Stock adjustment would result in negative stock, which is not allowed.",
            details={
                "current_quantity": exc.current_quantity,
                "requested_delta": exc.requested_delta,
                "adjustment_type": exc.adjustment_type,
                "resulting_quantity": exc.resulting_quantity,
            },
        ) from exc
    except repository.ProductNotFoundError as exc:
        raise NotFoundError(
            f"Product '{product_id}' not found.",
            details={"product_id": exc.product_id},
        ) from exc

    logger.info(
        "Stock adjustment applied",
        extra={
            "product_id": product_id,
            "adjustment_type": payload.adjustment_type,
            "delta": delta,
            "new_quantity": new_quantity,
        },
    )

    # Fetch product details to evaluate alert condition
    try:
        settings = get_settings()
        if settings.is_local and not settings.firestore_project_id:
            logger.info(
                "Skipping post-adjustment product lookup in local mode because Firestore is not configured",
                extra={"store_id": store_id, "product_id": product_id},
            )
            return {
                "product_id": product_id,
                "new_quantity_on_hand": new_quantity,
                "adjustment_id": adjustment_id,
                "updated_at": updated_at.isoformat(),
            }

        product_data = await repository.get_product_by_id(product_id)
        if product_data:
            reorder_thresh = int(product_data.get("reorder_threshold", 0))
            product_name = product_data.get("name", "Unknown Product")
            _schedule_low_stock_evaluation(
                store_id=store_id,
                product_id=product_id,
                product_name=product_name,
                current_stock=new_quantity,
                reorder_threshold=reorder_thresh,
            )
    except Exception as e:
        logger.error(f"Failed to trigger LOW_STOCK alert evaluation: {e}")

    return {
        "product_id": product_id,
        "new_quantity_on_hand": new_quantity,
        "adjustment_id": adjustment_id,
        "updated_at": updated_at.isoformat(),
    }


def _validate_store_scope(
    request_store_id: Optional[str],
    auth_store_id: str,
    allow_none: bool = False,
) -> None:
    if request_store_id is None and allow_none:
        return
    if request_store_id != auth_store_id:
        raise AppValidationError(
            "store_id in request must match authenticated store scope.",
            details={
                "request_store_id": request_store_id,
                "auth_store_id": auth_store_id,
            },
        )


def _parse_page_token(page_token: Optional[str]) -> int:
    if page_token is None:
        return 0
    if not page_token.isdigit():
        raise AppValidationError(
            "Invalid page_token. Expected a numeric token.",
            details={"page_token": page_token},
        )
    return int(page_token)
