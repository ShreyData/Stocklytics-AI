"""
Alerts Module – Repository layer.

Isolates all Firestore read/write operations for alerts.
The service layer calls only these functions; routes never touch Firestore directly.

Collections:
    alerts              – current alert state (one document per active condition)
    alerts/{id}/events  – immutable event log for each lifecycle transition
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

from app.common.config import get_settings
from app.common.google_clients import create_firestore_async_client

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
        _db = create_firestore_async_client(project=project)
    return _db


# ---------------------------------------------------------------------------
# Collection constants
# ---------------------------------------------------------------------------

ALERTS_COLLECTION = "alerts"
EVENTS_SUBCOLLECTION = "events"
PRODUCTS_COLLECTION = "products"
TRANSACTIONS_COLLECTION = "transactions"


# ---------------------------------------------------------------------------
# Alert repository functions
# ---------------------------------------------------------------------------

async def get_alert_by_id(alert_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single alert by its document ID. Returns None if not found."""
    db = _get_db()
    doc: DocumentSnapshot = await db.collection(ALERTS_COLLECTION).document(alert_id).get()
    if not doc.exists:
        return None
    return _snapshot_to_dict(doc)


async def get_alert_by_condition(store_id: str, condition_key: str) -> Optional[dict[str, Any]]:
    """
    Fetch the open (ACTIVE or ACKNOWLEDGED) alert for a given condition_key.
    Returns None if no open alert exists.
    """
    from app.modules.alerts.schemas import ALERT_STATUS_RESOLVED

    db = _get_db()
    query = db.collection(ALERTS_COLLECTION).where("store_id", "==", store_id)

    async for doc in query.stream():
        data = _snapshot_to_dict(doc)
        if data.get("condition_key") == condition_key and data.get("status") != ALERT_STATUS_RESOLVED:
            return data
    return None


async def list_alerts(
    store_id: str,
    status: Optional[str] = None,
    alert_type: Optional[str] = None,
    severity: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Return alerts for a store with optional filters.

    Args:
        store_id:   Firestore equality filter on store_id.
        status:     Optional filter by lifecycle status.
        alert_type: Optional filter by alert type.
        severity:   Optional filter by severity level.
    """
    db = _get_db()
    query = db.collection(ALERTS_COLLECTION).where("store_id", "==", store_id)

    results: list[dict[str, Any]] = []
    async for doc in query.stream():
        data = _snapshot_to_dict(doc)
        if status is not None and data.get("status") != status:
            continue
        if alert_type is not None and data.get("alert_type") != alert_type:
            continue
        if severity is not None and data.get("severity") != severity:
            continue
        results.append(data)
    return results


async def create_alert(alert_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new alert document and return the stored data."""
    db = _get_db()
    doc_ref = db.collection(ALERTS_COLLECTION).document(alert_id)
    await doc_ref.set(data)
    logger.info("Alert created", extra={"alert_id": alert_id, "store_id": data.get("store_id")})
    return data


async def update_alert(alert_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Apply a partial update to an alert document.

    Returns the updated document data, or None if the alert does not exist.
    """
    db = _get_db()
    doc_ref = db.collection(ALERTS_COLLECTION).document(alert_id)
    doc: DocumentSnapshot = await doc_ref.get()
    if not doc.exists:
        return None
    await doc_ref.update(updates)
    updated_doc: DocumentSnapshot = await doc_ref.get()
    logger.info("Alert updated", extra={"alert_id": alert_id})
    return _snapshot_to_dict(updated_doc)


async def write_alert_event(
    alert_id: str,
    event_id: str,
    event_data: dict[str, Any],
) -> None:
    """
    Write a lifecycle event document into the alerts/{alert_id}/events subcollection.

    Every status transition must produce one event record per alerts_logic.md §9.
    """
    db = _get_db()
    event_ref = (
        db.collection(ALERTS_COLLECTION)
        .document(alert_id)
        .collection(EVENTS_SUBCOLLECTION)
        .document(event_id)
    )
    await event_ref.set(event_data)
    logger.info(
        "Alert event written",
        extra={
            "alert_id": alert_id,
            "event_id": event_id,
            "to_status": event_data.get("to_status"),
        },
    )


async def list_products_for_store(store_id: str) -> list[dict[str, Any]]:
    """
    Return all products for a store.

    Alerts engine applies additional in-memory filters (for example, stock > 0)
    to keep this repository helper simple and index-safe.
    """
    db = _get_db()
    query = db.collection(PRODUCTS_COLLECTION).where("store_id", "==", store_id)

    results: list[dict[str, Any]] = []
    async for doc in query.stream():
        data = doc.to_dict() or {}
        data.setdefault("product_id", doc.id)
        results.append(data)
    return results


async def list_transactions_in_window(
    store_id: str,
    start_at: datetime,
    end_at: datetime,
) -> list[dict[str, Any]]:
    """
    Return transactions for a store inside [start_at, end_at] by sale_timestamp.
    """
    db = _get_db()
    query = db.collection(TRANSACTIONS_COLLECTION).where("store_id", "==", store_id)

    results: list[dict[str, Any]] = []
    async for doc in query.stream():
        data = doc.to_dict() or {}
        data.setdefault("transaction_id", doc.id)
        sale_timestamp = data.get("sale_timestamp")
        if not isinstance(sale_timestamp, datetime):
            continue
        if sale_timestamp < start_at or sale_timestamp > end_at:
            continue
        results.append(data)
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _snapshot_to_dict(snapshot: DocumentSnapshot) -> dict[str, Any]:
    """Convert a Firestore DocumentSnapshot to a plain dict, injecting the document ID."""
    data: dict[str, Any] = snapshot.to_dict() or {}  # type: ignore[assignment]
    # Firestore stores the primary key as the document ID, not a field.
    if "alert_id" not in data and snapshot.id:
        data["alert_id"] = snapshot.id
    return data
