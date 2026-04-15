"""
Billing Module – Repository layer.

Isolates every Firestore read/write for the billing domain.
The service layer is the only caller; routes never touch Firestore directly.

Collections used:
    transactions          – one document per completed billing transaction
    billing_idempotency   – idempotency key → stored result mapping
    products              – read-only; owned by Inventory module
    stock_adjustments     – write-only audit records created by billing

Firestore transaction:
    create_billing_transaction() executes a single atomic Firestore
    transaction that:
        1. Writes the transaction document.
        2. Updates each product's quantity_on_hand.
        3. Inserts a stock_adjustment record per line item.
        4. Writes the idempotency record.
    If any step fails the entire transaction is rolled back.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

from app.common.config import get_settings

logger = logging.getLogger(__name__)

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
        _db = firestore.AsyncClient(project=project)
    return _db


# ---------------------------------------------------------------------------
# Collection names
# ---------------------------------------------------------------------------

COL_TRANSACTIONS = "transactions"
COL_IDEMPOTENCY = "billing_idempotency"
COL_PRODUCTS = "products"
COL_ADJUSTMENTS = "stock_adjustments"


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

async def get_idempotency_record(
    store_id: str, idempotency_key: str
) -> Optional[dict[str, Any]]:
    """
    Look up an existing idempotency record.

    The document ID is ``{store_id}_{idempotency_key}`` to ensure keys are
    scoped per store and cannot collide across tenants.
    """
    db = _get_db()
    doc_id = _idempotency_doc_id(store_id, idempotency_key)
    doc: DocumentSnapshot = await db.collection(COL_IDEMPOTENCY).document(doc_id).get()
    if not doc.exists:
        return None
    return doc.to_dict()


async def get_products_by_ids(product_ids: list[str]) -> dict[str, dict[str, Any]]:
    """
    Batch-fetch product documents by ID.

    Returns a dict mapping product_id → document data.
    Missing products are absent from the result (caller must detect them).
    """
    db = _get_db()
    col = db.collection(COL_PRODUCTS)
    refs = [col.document(pid) for pid in product_ids]
    snapshots: list[DocumentSnapshot] = await db.get_all(refs)  # type: ignore[attr-defined]

    result: dict[str, dict[str, Any]] = {}
    for snap in snapshots:
        if snap.exists:
            data = snap.to_dict() or {}
            pid = data.get("product_id") or snap.id
            result[pid] = data
    return result


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

async def create_billing_transaction(
    *,
    transaction_id: str,
    transaction_doc: dict[str, Any],
    idempotency_doc_id: str,
    idempotency_doc: dict[str, Any],
    stock_updates: list[dict[str, Any]],
    adjustment_docs: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """
    Execute a single Firestore transaction that atomically:

    1. Writes the ``transactions`` document.
    2. Decrements ``quantity_on_hand`` on each product.
    3. Inserts a ``stock_adjustments`` record per line item.
    4. Writes the ``billing_idempotency`` record.

    If any step fails, Firestore rolls back all writes automatically.

    Args:
        transaction_id:     The new transaction's document ID.
        transaction_doc:    Full transaction document data.
        idempotency_doc_id: Pre-computed idempotency doc ID.
        idempotency_doc:    Idempotency document data to store.
        stock_updates:      List of {product_id, new_quantity} dicts.
        adjustment_docs:    List of (adjustment_id, adjustment_doc) tuples.

    Returns:
        The transaction document data that was written.
    """
    db = _get_db()

    async with db.transaction() as tx:  # type: ignore[attr-defined]
        col_txn = db.collection(COL_TRANSACTIONS)
        col_idp = db.collection(COL_IDEMPOTENCY)
        col_prod = db.collection(COL_PRODUCTS)
        col_adj = db.collection(COL_ADJUSTMENTS)

        now = datetime.now(timezone.utc)

        # 1. Write transaction document
        tx.set(col_txn.document(transaction_id), transaction_doc)

        # 2. Update stock levels
        for upd in stock_updates:
            tx.update(
                col_prod.document(upd["product_id"]),
                {
                    "quantity_on_hand": upd["new_quantity"],
                    "updated_at": now,
                },
            )

        # 3. Insert stock_adjustment audit records
        for adj_id, adj_doc in adjustment_docs:
            tx.set(col_adj.document(adj_id), adj_doc)

        # 4. Save idempotency record
        tx.set(col_idp.document(idempotency_doc_id), idempotency_doc)

    logger.info(
        "Billing transaction committed",
        extra={
            "transaction_id": transaction_id,
            "idempotency_doc_id": idempotency_doc_id,
        },
    )
    return transaction_doc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _idempotency_doc_id(store_id: str, idempotency_key: str) -> str:
    """
    Build the Firestore document ID for an idempotency record.

    Scoped per store so the same key cannot clash across tenants.
    The separator ``::`` is URL-safe and unlikely to appear in user keys.
    """
    return f"{store_id}::{idempotency_key}"


# Expose helper so the service can use it without re-importing internals.
get_idempotency_doc_id = _idempotency_doc_id
