"""
Inventory Module – Repository layer.

Isolates all Firestore read/write operations. The service layer
calls only these functions; routes never touch Firestore directly.

Collections:
    products           – product master records
    stock_adjustments  – immutable audit log of every stock change
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

from app.common.config import get_settings
from app.common.google_clients import create_firestore_async_client

logger = logging.getLogger(__name__)


class NegativeStockError(Exception):
    """Raised when an adjustment would reduce stock below zero."""

    def __init__(
        self,
        current_quantity: int,
        requested_delta: int,
        adjustment_type: str,
        resulting_quantity: int,
    ) -> None:
        super().__init__("Negative stock is not allowed.")
        self.current_quantity = current_quantity
        self.requested_delta = requested_delta
        self.adjustment_type = adjustment_type
        self.resulting_quantity = resulting_quantity


class ProductNotFoundError(Exception):
    """Raised when a product does not exist in the requested store scope."""

    def __init__(self, product_id: str) -> None:
        super().__init__(f"Product '{product_id}' not found.")
        self.product_id = product_id

# ---------------------------------------------------------------------------
# Firestore client (lazy singleton)
# ---------------------------------------------------------------------------

_db: Optional[firestore.AsyncClient] = None


def _get_db() -> firestore.AsyncClient:
    """Return a cached Firestore async client, initialising on first call."""
    global _db
    if _db is None:
        settings = get_settings()
        project = settings.firestore_project_id or None
        _db = create_firestore_async_client(project=project)
    return _db


# ---------------------------------------------------------------------------
# Collection references
# ---------------------------------------------------------------------------

PRODUCTS_COLLECTION = "products"
ADJUSTMENTS_COLLECTION = "stock_adjustments"


# ---------------------------------------------------------------------------
# Product repository functions
# ---------------------------------------------------------------------------

async def create_product(product_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new product document and return the stored data."""
    db = _get_db()
    doc_ref = db.collection(PRODUCTS_COLLECTION).document(product_id)
    await doc_ref.set(data)
    logger.info("Product created", extra={"product_id": product_id})
    return data


async def get_product_by_id(product_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single product by its ID. Returns None if not found."""
    db = _get_db()
    doc: DocumentSnapshot = await db.collection(PRODUCTS_COLLECTION).document(product_id).get()
    if not doc.exists:
        return None
    return _snapshot_to_dict(doc)


async def list_products(
    store_id: str,
    low_stock_only: bool = False,
    expiry_before: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """
    List products for a given store with optional filters.

    Args:
        store_id:      Filter to products belonging to this store.
        low_stock_only: If True, only return products where quantity_on_hand
                        is less than or equal to reorder_threshold.
        expiry_before: If set, only return products whose expiry_date is
                       before this datetime.
    """
    db = _get_db()
    query = db.collection(PRODUCTS_COLLECTION).where("store_id", "==", store_id)

    if expiry_before is not None:
        query = query.where("expiry_date", "<", expiry_before)

    results: list[dict[str, Any]] = []
    docs = await query.get()
    for doc in docs:
        product = _snapshot_to_dict(doc)
        if low_stock_only:
            # Firestore cannot filter quantity_on_hand <= reorder_threshold
            # in a single compound query without a composite index, so we
            # filter client-side to avoid index management overhead.
            if product["quantity_on_hand"] > product["reorder_threshold"]:
                continue
        results.append(product)

    return results


async def update_product(product_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Apply a partial update to a product document.

    Returns the updated document data, or None if the product does not exist.
    """
    db = _get_db()
    doc_ref = db.collection(PRODUCTS_COLLECTION).document(product_id)
    doc: DocumentSnapshot = await doc_ref.get()
    if not doc.exists:
        return None
    await doc_ref.update(updates)
    updated_doc: DocumentSnapshot = await doc_ref.get()
    logger.info("Product updated", extra={"product_id": product_id})
    return _snapshot_to_dict(updated_doc)


# ---------------------------------------------------------------------------
# Stock adjustment repository functions
# ---------------------------------------------------------------------------

async def create_stock_adjustment(
    adjustment_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Insert an immutable stock adjustment audit record."""
    db = _get_db()
    doc_ref = db.collection(ADJUSTMENTS_COLLECTION).document(adjustment_id)
    await doc_ref.set(data)
    logger.info(
        "Stock adjustment recorded",
        extra={"adjustment_id": adjustment_id, "product_id": data.get("product_id")},
    )
    return data


async def apply_stock_adjustment_atomic(
    product_id: str,
    store_id: str,
    adjustment_type: str,
    quantity_delta: int,
    adjustment_doc: dict[str, Any],
    updated_at: Any,
) -> tuple[Any, int]:
    """
    Update stock and append audit record atomically in one Firestore transaction.

    Returns:
        tuple(updated_at, new_quantity_on_hand)
    """
    db = _get_db()
    transaction = db.transaction()
    product_ref = db.collection(PRODUCTS_COLLECTION).document(product_id)
    adjustment_ref = db.collection(ADJUSTMENTS_COLLECTION).document(adjustment_doc["adjustment_id"])

    @firestore.async_transactional
    async def _apply(txn: firestore.AsyncTransaction) -> int:
        snapshot: DocumentSnapshot = await product_ref.get(transaction=txn)
        if not snapshot.exists:
            raise ProductNotFoundError(product_id)

        product = _snapshot_to_dict(snapshot)
        if product.get("store_id") != store_id:
            raise ProductNotFoundError(product_id)

        current_quantity = int(product.get("quantity_on_hand", 0))
        is_subtraction = adjustment_type in {"REMOVE", "SALE_DEDUCTION"}
        new_quantity = current_quantity - quantity_delta if is_subtraction else current_quantity + quantity_delta

        if new_quantity < 0:
            raise NegativeStockError(
                current_quantity=current_quantity,
                requested_delta=quantity_delta,
                adjustment_type=adjustment_type,
                resulting_quantity=new_quantity,
            )

        txn.update(
            product_ref,
            {
                "quantity_on_hand": new_quantity,
                "updated_at": updated_at,
            },
        )
        txn.set(adjustment_ref, adjustment_doc)
        return new_quantity

    new_quantity = await _apply(transaction)
    logger.info(
        "Stock adjustment transaction committed",
        extra={
            "product_id": product_id,
            "adjustment_id": adjustment_doc["adjustment_id"],
            "new_quantity": new_quantity,
        },
    )
    return updated_at, new_quantity


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _snapshot_to_dict(snapshot: DocumentSnapshot) -> dict[str, Any]:
    """Convert a Firestore DocumentSnapshot to a plain dict, injecting the document ID."""
    data: dict[str, Any] = snapshot.to_dict() or {}  # type: ignore[assignment]
    # Ensure the primary key field is always present in the returned dict.
    # Firestore stores it as the document ID, not a field.
    if "product_id" not in data and snapshot.id:
        data["product_id"] = snapshot.id
    if "adjustment_id" not in data and snapshot.id:
        data["adjustment_id"] = snapshot.id
    return data
