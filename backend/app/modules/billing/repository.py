"""
Billing Module – Repository layer.

Isolates Firestore access for the billing domain.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

from app.common.config import get_settings
from app.common.google_clients import create_firestore_async_client

logger = logging.getLogger(__name__)


class BillingCommitProductNotFoundError(Exception):
    """Raised when a product disappears or leaves store scope during commit."""

    def __init__(self, product_id: str) -> None:
        super().__init__(f"Product '{product_id}' not found.")
        self.product_id = product_id


class BillingCommitInsufficientStockError(Exception):
    """Raised when stock is insufficient at commit time."""

    def __init__(
        self,
        product_id: str,
        requested_quantity: int,
        available_quantity: int,
    ) -> None:
        super().__init__(f"Insufficient stock for '{product_id}'.")
        self.product_id = product_id
        self.requested_quantity = requested_quantity
        self.available_quantity = available_quantity


class BillingCommitCustomerNotFoundError(Exception):
    """Raised when a customer cannot be found in the active store during commit."""

    def __init__(self, customer_id: str) -> None:
        super().__init__(f"Customer '{customer_id}' not found.")
        self.customer_id = customer_id


_db: Optional[firestore.AsyncClient] = None


def _get_db() -> firestore.AsyncClient:
    """Return a cached Firestore async client, initialising on first call."""
    global _db
    if _db is None:
        settings = get_settings()
        project = settings.firestore_project_id or None
        _db = create_firestore_async_client(project=project)
    return _db


COL_TRANSACTIONS = "transactions"
COL_IDEMPOTENCY = "billing_idempotency"
COL_PRODUCTS = "products"
COL_ADJUSTMENTS = "stock_adjustments"
COL_CUSTOMERS = "customers"


async def get_idempotency_record(
    store_id: str,
    idempotency_key: str,
) -> Optional[dict[str, Any]]:
    """Look up an existing idempotency record by composite key."""
    db = _get_db()
    doc_id = _idempotency_doc_id(store_id, idempotency_key)
    snapshot: DocumentSnapshot = await db.collection(COL_IDEMPOTENCY).document(doc_id).get()
    if not snapshot.exists:
        return None
    return snapshot.to_dict()


async def touch_idempotency_record(
    idempotency_doc_id: str,
    last_seen_at: datetime,
) -> None:
    """Update the replay timestamp on an existing idempotency record."""
    db = _get_db()
    await db.collection(COL_IDEMPOTENCY).document(idempotency_doc_id).update(
        {"last_seen_at": last_seen_at}
    )


async def get_products_by_ids(product_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-fetch product documents by ID."""
    db = _get_db()
    refs = [db.collection(COL_PRODUCTS).document(product_id) for product_id in product_ids]
    snapshots = await asyncio.gather(*(ref.get() for ref in refs))

    result: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        if snapshot.exists:
            data = snapshot.to_dict() or {}
            result[data.get("product_id") or snapshot.id] = data
    return result


async def list_transactions(
    store_id: str,
    from_timestamp: Optional[datetime] = None,
    to_timestamp: Optional[datetime] = None,
    customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List transactions for a store with optional filters."""
    db = _get_db()
    query = db.collection(COL_TRANSACTIONS).where("store_id", "==", store_id)

    if customer_id is not None:
        query = query.where("customer_id", "==", customer_id)
    if from_timestamp is not None:
        query = query.where("sale_timestamp", ">=", from_timestamp)
    if to_timestamp is not None:
        query = query.where("sale_timestamp", "<=", to_timestamp)

    docs = query.stream()
    results: list[dict[str, Any]] = []
    async for doc in docs:
        data = doc.to_dict() or {}
        data.setdefault("transaction_id", doc.id)
        results.append(data)

    results.sort(key=lambda item: item.get("sale_timestamp"), reverse=True)
    return results


async def get_transaction_by_id(transaction_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single transaction by document ID."""
    db = _get_db()
    snapshot: DocumentSnapshot = await db.collection(COL_TRANSACTIONS).document(transaction_id).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    data.setdefault("transaction_id", snapshot.id)
    return data


async def create_billing_transaction(
    *,
    transaction_id: str,
    transaction_doc: dict[str, Any],
    idempotency_doc_id: str,
    idempotency_key: str,
    store_id: str,
    request_hash: str,
    result_status: str,
    response_transaction: dict[str, Any],
    inventory_deductions: list[dict[str, Any]],
    adjustment_docs: list[tuple[str, dict[str, Any]]],
    created_at: datetime,
    customer_summary_update: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Execute a single atomic Firestore transaction for billing.

    Writes:
    - transactions document
    - stock deductions
    - stock adjustment audit rows
    - billing_idempotency document
    """
    db = _get_db()
    transaction_ref = db.collection(COL_TRANSACTIONS).document(transaction_id)
    idempotency_ref = db.collection(COL_IDEMPOTENCY).document(idempotency_doc_id)
    inventory_updates: list[dict[str, Any]] = []

    for deduction in inventory_deductions:
        product_id = deduction["product_id"]
        quantity_delta = int(deduction["quantity_delta"])
        product_ref = db.collection(COL_PRODUCTS).document(product_id)
        snapshot: DocumentSnapshot = await product_ref.get()

        if not snapshot.exists:
            raise BillingCommitProductNotFoundError(product_id)

        product = snapshot.to_dict() or {}
        if product.get("store_id") != store_id:
            raise BillingCommitProductNotFoundError(product_id)

        available_quantity = int(product.get("quantity_on_hand", 0))
        if quantity_delta > available_quantity:
            raise BillingCommitInsufficientStockError(
                product_id=product_id,
                requested_quantity=quantity_delta,
                available_quantity=available_quantity,
            )

        new_quantity = available_quantity - quantity_delta
        await product_ref.update(
            {
                "quantity_on_hand": new_quantity,
                "updated_at": created_at,
            }
        )
        inventory_updates.append(
            {
                "product_id": product_id,
                "new_quantity_on_hand": new_quantity,
            }
        )

    await transaction_ref.set(transaction_doc)

    for adjustment_id, adjustment_doc in adjustment_docs:
        await db.collection(COL_ADJUSTMENTS).document(adjustment_id).set(adjustment_doc)

    if customer_summary_update is not None:
        customer_id = customer_summary_update["customer_id"]
        customer_ref = db.collection(COL_CUSTOMERS).document(customer_id)
        customer_snapshot: DocumentSnapshot = await customer_ref.get()
        if not customer_snapshot.exists:
            raise BillingCommitCustomerNotFoundError(customer_id)

        customer_doc = customer_snapshot.to_dict() or {}
        if customer_doc.get("store_id") != store_id:
            raise BillingCommitCustomerNotFoundError(customer_id)

        current_total_spend = float(customer_doc.get("total_spend", 0.0))
        current_visit_count = int(customer_doc.get("visit_count", 0))
        sale_amount = float(customer_summary_update["sale_amount"])

        await customer_ref.update(
            {
                "total_spend": round(current_total_spend + sale_amount, 2),
                "visit_count": current_visit_count + 1,
                "last_purchase_at": customer_summary_update["sale_timestamp"],
                "updated_at": created_at,
            }
        )

    response_snapshot = {
        "idempotent_replay": False,
        "transaction": response_transaction,
        "inventory_updates": inventory_updates,
    }
    idempotency_doc = {
        "idempotency_record_id": idempotency_doc_id,
        "store_id": store_id,
        "idempotency_key": idempotency_key,
        "request_hash": request_hash,
        "transaction_id": transaction_id,
        "result_status": result_status,
        "response_snapshot": response_snapshot,
        "created_at": created_at,
        "last_seen_at": created_at,
    }
    await idempotency_ref.set(idempotency_doc)
    logger.info(
        "Billing transaction committed",
        extra={
            "transaction_id": transaction_id,
            "idempotency_key": idempotency_key,
        },
    )
    return response_snapshot


def _idempotency_doc_id(store_id: str, idempotency_key: str) -> str:
    """Build the Firestore document ID for an idempotency record."""
    return f"{store_id}_{idempotency_key}"


get_idempotency_doc_id = _idempotency_doc_id
