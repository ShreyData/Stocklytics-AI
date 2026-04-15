"""
Billing Module – Service layer.

All business logic lives here. Routes are thin wrappers around these functions.

Business rules enforced:
    1. Every request MUST supply an idempotency_key.
    2. Same key + same payload  → idempotent replay (return stored result, 200).
    3. Same key + different payload → 409 IDEMPOTENCY_KEY_CONFLICT.
    4. ALL products must exist before any write begins.
    5. ALL stock levels must be sufficient before any write begins.
    6. The Firestore transaction is strictly atomic:
           – transaction record
           – stock deductions
           – stock_adjustment audit rows
           – idempotency record
       If anything fails → full rollback; no partial writes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.common.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError as AppValidationError,
)
from app.modules.billing import repository
from app.modules.billing.schemas import TransactionCreateRequest

logger = logging.getLogger(__name__)

# Adjustment type written to stock_adjustments for billing deductions
ADJUSTMENT_TYPE_SALE_DEDUCTION = "SALE_DEDUCTION"


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------

def _payload_hash(payload: TransactionCreateRequest) -> str:
    """
    Produce a stable SHA-256 fingerprint of the request payload.

    Only ``items`` is included (not ``notes``, which is non-semantic).
    Items are sorted by product_id so order variation is ignored.
    """
    canonical = sorted(
        [
            {"product_id": item.product_id, "quantity": item.quantity, "unit_price": item.unit_price}
            for item in payload.items
        ],
        key=lambda x: x["product_id"],
    )
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------

def _firestore_to_response(data: dict[str, Any]) -> dict[str, Any]:
    """Convert Firestore timestamp objects to ISO-8601 strings for JSON serialisation."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            result[key] = value.isoformat()
        elif isinstance(value, list):
            result[key] = [
                _firestore_to_response(v) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Core service function
# ---------------------------------------------------------------------------

async def create_transaction(
    payload: TransactionCreateRequest,
    store_id: str,
    user_id: str,
) -> tuple[dict[str, Any], int]:
    """
    Create a billing transaction atomically.

    Returns:
        (transaction_dict, http_status_code)
        http_status_code is 200 for idempotent replays, 201 for new transactions.

    Raises:
        ConflictError   – same idempotency_key with a different payload.
        NotFoundError   – one or more product_ids do not exist in the store.
        AppValidationError – insufficient stock for one or more items.
    """
    # ------------------------------------------------------------------
    # Step 1 – Check idempotency
    # ------------------------------------------------------------------
    idempotency_doc_id = repository.get_idempotency_doc_id(store_id, payload.idempotency_key)
    existing = await repository.get_idempotency_record(store_id, payload.idempotency_key)
    incoming_hash = _payload_hash(payload)

    if existing is not None:
        stored_hash: str = existing.get("payload_hash", "")
        if stored_hash == incoming_hash:
            # Exact replay – return the original result unchanged
            logger.info(
                "Idempotent replay",
                extra={"idempotency_key": payload.idempotency_key, "store_id": store_id},
            )
            stored_txn: dict[str, Any] = existing.get("transaction_snapshot", {})
            return _firestore_to_response(stored_txn), 200
        else:
            raise ConflictError(
                "The idempotency_key has already been used with a different request payload.",
                details={
                    "idempotency_key": payload.idempotency_key,
                    "error_code": "IDEMPOTENCY_KEY_CONFLICT",
                },
            )

    # ------------------------------------------------------------------
    # Step 2 – Fetch all products (read-only phase, before any writes)
    # ------------------------------------------------------------------
    requested_product_ids = [item.product_id for item in payload.items]
    products = await repository.get_products_by_ids(requested_product_ids)

    # Check every product exists and belongs to this store
    missing: list[str] = []
    wrong_store: list[str] = []
    for pid in requested_product_ids:
        if pid not in products:
            missing.append(pid)
        elif products[pid].get("store_id") != store_id:
            wrong_store.append(pid)

    not_found = missing + wrong_store
    if not_found:
        raise NotFoundError(
            "One or more products were not found in this store.",
            details={"missing_product_ids": not_found},
        )

    # ------------------------------------------------------------------
    # Step 3 – Validate stock for ALL items (fail-fast, no partial writes)
    # ------------------------------------------------------------------
    insufficient: list[dict[str, Any]] = []
    for item in payload.items:
        product = products[item.product_id]
        current_qty: int = product.get("quantity_on_hand", 0)
        if item.quantity > current_qty:
            insufficient.append(
                {
                    "product_id": item.product_id,
                    "requested": item.quantity,
                    "available": current_qty,
                }
            )

    if insufficient:
        raise AppValidationError(
            "Insufficient stock for one or more items. No stock was deducted.",
            details={"insufficient_items": insufficient},
        )

    # ------------------------------------------------------------------
    # Step 4 – Build all write payloads (before entering the transaction)
    # ------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    transaction_id = f"txn_{uuid.uuid4().hex}"

    # Compute line items with totals
    line_items: list[dict[str, Any]] = []
    total_amount: float = 0.0
    stock_updates: list[dict[str, Any]] = []
    adjustment_docs: list[tuple[str, dict[str, Any]]] = []

    for item in payload.items:
        product = products[item.product_id]
        line_total = round(item.quantity * item.unit_price, 2)
        total_amount += line_total

        line_items.append(
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": line_total,
            }
        )

        new_quantity: int = product["quantity_on_hand"] - item.quantity
        stock_updates.append(
            {"product_id": item.product_id, "new_quantity": new_quantity}
        )

        adj_id = f"adj_{uuid.uuid4().hex}"
        adjustment_docs.append(
            (
                adj_id,
                {
                    "adjustment_id": adj_id,
                    "store_id": store_id,
                    "product_id": item.product_id,
                    "adjustment_type": ADJUSTMENT_TYPE_SALE_DEDUCTION,
                    "quantity_delta": item.quantity,
                    "reason": f"Billing transaction {transaction_id}",
                    "source_ref": transaction_id,
                    "created_by": user_id,
                    "created_at": now,
                },
            )
        )

    total_amount = round(total_amount, 2)

    transaction_doc: dict[str, Any] = {
        "transaction_id": transaction_id,
        "store_id": store_id,
        "idempotency_key": payload.idempotency_key,
        "items": line_items,
        "total_amount": total_amount,
        "status": "COMPLETED",
        "notes": payload.notes,
        "created_by": user_id,
        "created_at": now,
    }

    idempotency_doc: dict[str, Any] = {
        "idempotency_key": payload.idempotency_key,
        "store_id": store_id,
        "payload_hash": incoming_hash,
        "transaction_id": transaction_id,
        "transaction_snapshot": transaction_doc,
        "created_at": now,
    }

    # ------------------------------------------------------------------
    # Step 5 – Execute atomic Firestore transaction
    # ------------------------------------------------------------------
    stored = await repository.create_billing_transaction(
        transaction_id=transaction_id,
        transaction_doc=transaction_doc,
        idempotency_doc_id=idempotency_doc_id,
        idempotency_doc=idempotency_doc,
        stock_updates=stock_updates,
        adjustment_docs=adjustment_docs,
    )

    logger.info(
        "Billing transaction created",
        extra={
            "transaction_id": transaction_id,
            "store_id": store_id,
            "total_amount": total_amount,
            "line_items": len(line_items),
        },
    )

    return _firestore_to_response(stored), 201
