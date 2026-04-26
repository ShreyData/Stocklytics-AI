"""
Billing Module – Service layer.

All business logic lives here. Routes are thin wrappers around these functions.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.common.config import get_settings
from app.common.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError as AppValidationError,
)
from app.modules.alerts.engine import evaluate_low_stock
from app.modules.billing import repository
from app.modules.billing.schemas import (
    TRANSACTION_STATUS_COMPLETED,
    TransactionCreateRequest,
)

logger = logging.getLogger(__name__)

ADJUSTMENT_TYPE_SALE_DEDUCTION = "SALE_DEDUCTION"


class InvalidBillingQueryError(AppValidationError):
    """Raised when billing list query parameters are invalid."""

    error_code = "INVALID_QUERY"


class BillingProductNotFoundError(NotFoundError):
    """Raised when a billing product cannot be found in the active store."""

    error_code = "PRODUCT_NOT_FOUND"


class BillingTransactionNotFoundError(NotFoundError):
    """Raised when a transaction cannot be found in the active store."""

    error_code = "TRANSACTION_NOT_FOUND"


class BillingCustomerNotFoundError(NotFoundError):
    """Raised when a customer cannot be found in the active store."""

    error_code = "CUSTOMER_NOT_FOUND"


class IdempotencyKeyConflictError(ConflictError):
    """Raised when the same idempotency key is reused with a different payload."""

    error_code = "IDEMPOTENCY_KEY_CONFLICT"


class InsufficientStockError(ConflictError):
    """Raised when one or more requested items exceed available stock."""

    error_code = "INSUFFICIENT_STOCK"


def _payload_hash(payload: TransactionCreateRequest) -> str:
    """
    Produce a stable SHA-256 fingerprint of the billing request.

    Sorting items by product_id makes retries stable even if item order changes.
    """
    canonical = {
        "store_id": payload.store_id,
        "customer_id": payload.customer_id,
        "payment_method": payload.payment_method,
        "items": sorted(
            [
                {"product_id": item.product_id, "quantity": item.quantity}
                for item in payload.items
            ],
            key=lambda item: item["product_id"],
        ),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _firestore_to_response(data: dict[str, Any]) -> dict[str, Any]:
    """Convert Firestore timestamps into ISO-8601 strings."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            result[key] = value.isoformat()
        elif isinstance(value, list):
            result[key] = [
                _firestore_to_response(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, dict):
            result[key] = _firestore_to_response(value)
        else:
            result[key] = value
    return result


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
        raise InvalidBillingQueryError(
            "Invalid page_token. Expected a numeric token.",
            details={"page_token": page_token},
        )
    return int(page_token)


def _build_replay_response(response_snapshot: dict[str, Any]) -> dict[str, Any]:
    transaction = response_snapshot.get("transaction", {})
    return {
        "idempotent_replay": True,
        "transaction": {
            "transaction_id": transaction.get("transaction_id"),
            "status": transaction.get("status"),
            "total_amount": transaction.get("total_amount"),
        },
    }


def _build_transaction_detail(transaction_doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "transaction_id": transaction_doc["transaction_id"],
        "store_id": transaction_doc["store_id"],
        "customer_id": transaction_doc.get("customer_id"),
        "status": transaction_doc["status"],
        "payment_method": transaction_doc["payment_method"],
        "total_amount": transaction_doc["total_amount"],
        "sale_timestamp": transaction_doc["sale_timestamp"],
        "idempotency_key": transaction_doc["idempotency_key"],
        "items": [
            {
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "line_total": item["line_total"],
            }
            for item in transaction_doc.get("items", [])
        ],
    }


def _schedule_low_stock_evaluation(
    *,
    store_id: str,
    product_id: str,
    product_name: str,
    current_stock: int,
    reorder_threshold: int,
) -> None:
    """
    Schedule post-billing low-stock evaluation without blocking the API response.

    In local mode without Firestore configured, skip the cross-module hook so tests
    and bootstrap validation do not accidentally trigger real dependency work.
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
                "Low-stock evaluation failed after billing",
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


async def create_transaction(
    payload: TransactionCreateRequest,
    store_id: str,
    user_id: str,
) -> tuple[dict[str, Any], int]:
    """
    Create a billing transaction atomically.

    Returns:
        tuple(payload, http_status_code)
    """
    _validate_store_scope(payload.store_id, store_id)

    idempotency_doc_id = repository.get_idempotency_doc_id(
        store_id, payload.idempotency_key
    )
    existing = await repository.get_idempotency_record(store_id, payload.idempotency_key)
    incoming_hash = _payload_hash(payload)
    now = datetime.now(timezone.utc)

    if existing is not None:
        stored_hash = existing.get("request_hash", "")
        if stored_hash == incoming_hash:
            await repository.touch_idempotency_record(idempotency_doc_id, now)
            response_snapshot = existing.get("response_snapshot", {})
            return _firestore_to_response(_build_replay_response(response_snapshot)), 200

        raise IdempotencyKeyConflictError(
            "The idempotency_key has already been used with a different request payload.",
            details={"idempotency_key": payload.idempotency_key},
        )

    requested_quantities: dict[str, int] = {}
    for item in payload.items:
        requested_quantities[item.product_id] = (
            requested_quantities.get(item.product_id, 0) + item.quantity
        )

    products = await repository.get_products_by_ids(list(requested_quantities.keys()))

    missing_or_wrong_store: list[str] = []
    for product_id in requested_quantities:
        if product_id not in products or products[product_id].get("store_id") != store_id:
            missing_or_wrong_store.append(product_id)

    if missing_or_wrong_store:
        raise BillingProductNotFoundError(
            "One or more products were not found in this store.",
            details={"missing_product_ids": missing_or_wrong_store},
        )

    failed_items: list[dict[str, Any]] = []
    for product_id, requested_quantity in requested_quantities.items():
        available_quantity = int(products[product_id].get("quantity_on_hand", 0))
        if requested_quantity > available_quantity:
            failed_items.append(
                {
                    "product_id": product_id,
                    "requested_quantity": requested_quantity,
                    "available_quantity": available_quantity,
                }
            )

    if failed_items:
        raise InsufficientStockError(
            "One or more products do not have enough stock.",
            details={"failed_items": failed_items},
        )

    transaction_id = f"txn_{uuid.uuid4().hex}"
    sale_timestamp = now
    total_amount = 0.0
    stored_items: list[dict[str, Any]] = []
    response_items: list[dict[str, Any]] = []
    adjustment_docs: list[tuple[str, dict[str, Any]]] = []

    for item in payload.items:
        product = products[item.product_id]
        unit_price = float(product.get("price", 0.0))
        line_total = round(item.quantity * unit_price, 2)
        total_amount += line_total

        stored_items.append(
            {
                "product_id": item.product_id,
                "product_name": product.get("name"),
                "quantity": item.quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )
        response_items.append(
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

        adjustment_id = f"adj_{uuid.uuid4().hex}"
        adjustment_docs.append(
            (
                adjustment_id,
                {
                    "adjustment_id": adjustment_id,
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

    inventory_deductions = [
        {"product_id": product_id, "quantity_delta": quantity_delta}
        for product_id, quantity_delta in requested_quantities.items()
    ]

    transaction_doc = {
        "transaction_id": transaction_id,
        "store_id": store_id,
        "idempotency_key": payload.idempotency_key,
        "customer_id": payload.customer_id,
        "status": TRANSACTION_STATUS_COMPLETED,
        "payment_method": payload.payment_method,
        "total_amount": total_amount,
        "sale_timestamp": sale_timestamp,
        "items": stored_items,
        "created_by": user_id,
        "created_at": now,
    }

    customer_summary_update: Optional[dict[str, Any]] = None
    if payload.customer_id:
        customer_summary_update = {
            "customer_id": payload.customer_id,
            "sale_amount": total_amount,
            "sale_timestamp": sale_timestamp,
        }

    response_transaction = {
        "transaction_id": transaction_id,
        "store_id": store_id,
        "customer_id": payload.customer_id,
        "status": TRANSACTION_STATUS_COMPLETED,
        "payment_method": payload.payment_method,
        "total_amount": total_amount,
        "sale_timestamp": sale_timestamp,
        "items": response_items,
    }

    try:
        stored_response = await repository.create_billing_transaction(
            transaction_id=transaction_id,
            transaction_doc=transaction_doc,
            idempotency_doc_id=idempotency_doc_id,
            idempotency_key=payload.idempotency_key,
            store_id=store_id,
            request_hash=incoming_hash,
            result_status=TRANSACTION_STATUS_COMPLETED,
            response_transaction=response_transaction,
            inventory_deductions=inventory_deductions,
            adjustment_docs=adjustment_docs,
            created_at=now,
            customer_summary_update=customer_summary_update,
        )
    except repository.BillingCommitProductNotFoundError as exc:
        raise BillingProductNotFoundError(
            "One or more products were not found in this store.",
            details={"missing_product_ids": [exc.product_id]},
        ) from exc
    except repository.BillingCommitInsufficientStockError as exc:
        raise InsufficientStockError(
            "One or more products do not have enough stock.",
            details={
                "failed_items": [
                    {
                        "product_id": exc.product_id,
                        "requested_quantity": exc.requested_quantity,
                        "available_quantity": exc.available_quantity,
                    }
                ]
            },
        ) from exc
    except repository.BillingCommitCustomerNotFoundError as exc:
        raise BillingCustomerNotFoundError(
            "Customer was not found in this store.",
            details={"customer_id": exc.customer_id},
        ) from exc

    # Evaluate LOW_STOCK alerts post-transaction
    if not stored_response.get("idempotent_replay"):
        inventory_updates = stored_response.get("inventory_updates", [])
        for update in inventory_updates:
            prod_id = update.get("product_id")
            new_qty = update.get("new_quantity_on_hand", 0)
            product_doc = products.get(prod_id, {})
            reorder_thresh = int(product_doc.get("reorder_threshold", 0))
            product_name = product_doc.get("name", "Unknown Product")

            _schedule_low_stock_evaluation(
                store_id=store_id,
                product_id=prod_id,
                product_name=product_name,
                current_stock=new_qty,
                reorder_threshold=reorder_thresh,
            )

    logger.info(
        "Billing transaction created",
        extra={
            "transaction_id": transaction_id,
            "store_id": store_id,
            "idempotency_key": payload.idempotency_key,
            "total_amount": total_amount,
        },
    )
    return _firestore_to_response(stored_response), 201


async def list_transactions(
    store_id: str,
    requested_store_id: Optional[str] = None,
    from_timestamp: Optional[datetime] = None,
    to_timestamp: Optional[datetime] = None,
    customer_id: Optional[str] = None,
    limit: int = 50,
    page_token: Optional[str] = None,
) -> dict[str, Any]:
    _validate_store_scope(requested_store_id, store_id, allow_none=True)

    if (
        from_timestamp is not None
        and to_timestamp is not None
        and from_timestamp > to_timestamp
    ):
        raise InvalidBillingQueryError(
            "`from` must be earlier than or equal to `to`.",
            details={
                "from": from_timestamp.isoformat(),
                "to": to_timestamp.isoformat(),
            },
        )

    transactions = await repository.list_transactions(
        store_id=store_id,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        customer_id=customer_id,
    )
    start_idx = _parse_page_token(page_token)
    if start_idx >= len(transactions):
        return {"items": [], "next_page_token": None}

    page = transactions[start_idx:start_idx + limit]
    next_idx = start_idx + limit
    next_page_token = str(next_idx) if next_idx < len(transactions) else None

    return {
        "items": [
            _firestore_to_response(
                {
                    "transaction_id": transaction["transaction_id"],
                    "customer_id": transaction.get("customer_id"),
                    "total_amount": transaction["total_amount"],
                    "sale_timestamp": transaction["sale_timestamp"],
                    "status": transaction["status"],
                }
            )
            for transaction in page
        ],
        "next_page_token": next_page_token,
    }


async def get_transaction(
    transaction_id: str,
    store_id: str,
) -> dict[str, Any]:
    transaction = await repository.get_transaction_by_id(transaction_id)
    if transaction is None or transaction.get("store_id") != store_id:
        raise BillingTransactionNotFoundError(
            f"Transaction '{transaction_id}' not found.",
            details={"transaction_id": transaction_id},
        )
    return _firestore_to_response(_build_transaction_detail(transaction))
