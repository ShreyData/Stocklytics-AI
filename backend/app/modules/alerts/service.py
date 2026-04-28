"""
Alerts Module – Service layer.

Contains all business logic for alert lifecycle management.
Routes are thin; all domain decisions live here.

Business rules enforced here (per alerts_logic.md and alerts_implementation.md):
    1. Only one non-resolved alert should exist per condition_key.
    2. Lifecycle: ACTIVE -> ACKNOWLEDGED -> RESOLVED
                  ACTIVE -> RESOLVED  (direct shortcut is allowed)
    3. ACKNOWLEDGED -> ACTIVE is NOT allowed.
    4. RESOLVED is a terminal state – no further transitions.
    5. Every status transition writes an event into alerts/{alert_id}/events.
    6. store_id on the request must always match the authenticated store scope.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.common.exceptions import NotFoundError, ConflictError, ValidationError as AppValidationError
from app.modules.alerts import repository
from app.modules.alerts.schemas import (
    ALERT_STATUS_ACTIVE,
    ALERT_STATUS_ACKNOWLEDGED,
    ALERT_STATUS_RESOLVED,
    ALLOWED_TRANSITIONS,
    AcknowledgeRequest,
    ResolveRequest,
)

logger = logging.getLogger(__name__)


class AlertNotFoundError(NotFoundError):
    """Raised when an alert does not exist in the active store scope."""

    error_code = "ALERT_NOT_FOUND"


class InvalidAlertTransitionError(ConflictError):
    """Raised when an alert lifecycle transition is not allowed."""

    error_code = "INVALID_ALERT_TRANSITION"


async def _reconcile_inventory_backed_alerts(store_id: str) -> None:
    """
    Backfill product-driven alerts from the current inventory state.

    This keeps the alerts collection aligned with the operational dashboard when
    alert hooks were missed earlier or the alerts collection was empty.
    """
    from app.modules.alerts.engine import evaluate_expiry_soon, evaluate_low_stock

    products = await repository.list_products_for_store(store_id)
    for product in products:
        if product.get("status") == "INACTIVE":
            continue

        product_id = str(product.get("product_id") or "")
        if not product_id:
            continue

        await evaluate_low_stock(
            store_id=store_id,
            product_id=product_id,
            product_name=str(product.get("name") or "Unknown Product"),
            current_stock=int(product.get("quantity_on_hand", 0)),
            reorder_threshold=int(product.get("reorder_threshold", 0)),
        )
        await evaluate_expiry_soon(
            store_id=store_id,
            product_id=product_id,
            product_name=str(product.get("name") or "Unknown Product"),
            expiry_date=product.get("expiry_date"),
            current_stock=int(product.get("quantity_on_hand", 0)),
        )


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------

def _firestore_to_response(data: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a Firestore document dict to a JSON-serialisable response dict.

    Firestore timestamps are google.cloud.firestore.DatetimeWithNanoseconds
    objects; we normalise them to ISO-8601 strings (timezone-aware UTC).
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def _to_alert_list_item(alert: dict[str, Any]) -> dict[str, Any]:
    """Return the contract-shaped payload for GET /alerts list items."""
    return {
        "alert_id": alert.get("alert_id"),
        "alert_type": alert.get("alert_type"),
        "status": alert.get("status"),
        "severity": alert.get("severity"),
        "title": alert.get("title"),
        "message": alert.get("message"),
        "created_at": alert.get("created_at"),
        "acknowledged_at": alert.get("acknowledged_at"),
        "resolved_at": alert.get("resolved_at"),
    }


def _to_acknowledge_response(alert: dict[str, Any]) -> dict[str, Any]:
    """Return the contract-shaped payload for acknowledge responses."""
    return {
        "alert_id": alert.get("alert_id"),
        "status": alert.get("status"),
        "acknowledged_at": alert.get("acknowledged_at"),
        "acknowledged_by": alert.get("acknowledged_by"),
    }


def _to_resolve_response(alert: dict[str, Any]) -> dict[str, Any]:
    """Return the contract-shaped payload for resolve responses."""
    return {
        "alert_id": alert.get("alert_id"),
        "status": alert.get("status"),
        "resolved_at": alert.get("resolved_at"),
        "resolved_by": alert.get("resolved_by"),
        "resolution_note": alert.get("resolution_note"),
    }


# ---------------------------------------------------------------------------
# Store-scope validation helper
# ---------------------------------------------------------------------------

def _validate_store_scope(request_store_id: str, auth_store_id: str) -> None:
    """Raise ValidationError if the request store_id doesn't match the auth scope."""
    if request_store_id != auth_store_id:
        raise AppValidationError(
            "store_id in request must match authenticated store scope.",
            details={
                "request_store_id": request_store_id,
                "auth_store_id": auth_store_id,
            },
        )


# ---------------------------------------------------------------------------
# Alert list and summary
# ---------------------------------------------------------------------------

async def list_alerts(
    store_id: str,
    status: Optional[str] = None,
    alert_type: Optional[str] = None,
    severity: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Return alerts for a store, with optional status / type / severity filters.

    Filters are applied in Firestore where possible; no client-side post-filtering needed.
    """
    alerts = await repository.list_alerts(
        store_id=store_id,
        status=status,
        alert_type=alert_type,
        severity=severity,
    )

    if not alerts:
        await _reconcile_inventory_backed_alerts(store_id)
        alerts = await repository.list_alerts(
            store_id=store_id,
            status=status,
            alert_type=alert_type,
            severity=severity,
        )

    return [_to_alert_list_item(_firestore_to_response(alert)) for alert in alerts]


async def get_alerts_summary(store_id: str) -> dict[str, Any]:
    """
    Return alert counts grouped by status for dashboard cards.

    Returns:
        {"active": int, "acknowledged": int, "resolved_today": int}

    `resolved_today` counts alerts resolved on the current UTC calendar day.
    """
    all_alerts = await repository.list_alerts(store_id=store_id)

    if not all_alerts:
        await _reconcile_inventory_backed_alerts(store_id)
        all_alerts = await repository.list_alerts(store_id=store_id)

    today_utc = datetime.now(timezone.utc).date()
    active = 0
    acknowledged = 0
    resolved_today = 0

    for alert in all_alerts:
        s = alert.get("status")
        if s == ALERT_STATUS_ACTIVE:
            active += 1
        elif s == ALERT_STATUS_ACKNOWLEDGED:
            acknowledged += 1
        elif s == ALERT_STATUS_RESOLVED:
            resolved_at = alert.get("resolved_at")
            if resolved_at is not None:
                if isinstance(resolved_at, datetime):
                    if resolved_at.tzinfo is None:
                        resolved_at = resolved_at.replace(tzinfo=timezone.utc)
                    if resolved_at.date() == today_utc:
                        resolved_today += 1

    return {
        "active": active,
        "acknowledged": acknowledged,
        "resolved_today": resolved_today,
    }


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

async def acknowledge_alert(
    alert_id: str,
    store_id: str,
    user_id: str,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """
    Move an alert from ACTIVE to ACKNOWLEDGED.

    Rules (per alerts_logic.md §6):
        - Only ACTIVE alerts can be acknowledged.
        - Sets acknowledged_at and acknowledged_by.
        - Writes a lifecycle event to alerts/{alert_id}/events.

    Raises:
        NotFoundError: alert_id not found or belongs to another store.
        ConflictError: current status does not allow the ACKNOWLEDGED transition.
    """
    alert = await _fetch_and_validate_alert(alert_id, store_id)
    current_status: str = alert.get("status", "")

    _validate_transition(alert_id, current_status, ALERT_STATUS_ACKNOWLEDGED)

    now = datetime.now(timezone.utc)
    updates: dict[str, Any] = {
        "status": ALERT_STATUS_ACKNOWLEDGED,
        "acknowledged_at": now,
        "acknowledged_by": user_id,
    }
    updated = await repository.update_alert(alert_id, updates)
    if updated is None:
        raise AlertNotFoundError(
            f"Alert '{alert_id}' disappeared during update.",
            details={"alert_id": alert_id},
        )

    await _write_event(
        alert_id=alert_id,
        from_status=current_status,
        to_status=ALERT_STATUS_ACKNOWLEDGED,
        changed_by=user_id,
        note=note,
        changed_at=now,
    )

    logger.info(
        "Alert acknowledged",
        extra={"alert_id": alert_id, "user_id": user_id, "store_id": store_id},
    )
    return _to_acknowledge_response(_firestore_to_response(updated))


async def resolve_alert(
    alert_id: str,
    store_id: str,
    user_id: str,
    resolution_note: Optional[str] = None,
) -> dict[str, Any]:
    """
    Move an alert from ACTIVE or ACKNOWLEDGED to RESOLVED.

    Rules (per alerts_logic.md §6):
        - ACTIVE and ACKNOWLEDGED alerts can be resolved.
        - RESOLVED is a terminal state; trying to resolve again yields 409.
        - Sets resolved_at, resolved_by, resolution_note.
        - Writes a lifecycle event to alerts/{alert_id}/events.

    Raises:
        NotFoundError: alert_id not found or belongs to another store.
        ConflictError: current status does not allow the RESOLVED transition.
    """
    alert = await _fetch_and_validate_alert(alert_id, store_id)
    current_status: str = alert.get("status", "")

    _validate_transition(alert_id, current_status, ALERT_STATUS_RESOLVED)

    now = datetime.now(timezone.utc)
    updates: dict[str, Any] = {
        "status": ALERT_STATUS_RESOLVED,
        "resolved_at": now,
        "resolved_by": user_id,
        "resolution_note": resolution_note,
    }
    updated = await repository.update_alert(alert_id, updates)
    if updated is None:
        raise AlertNotFoundError(
            f"Alert '{alert_id}' disappeared during update.",
            details={"alert_id": alert_id},
        )

    await _write_event(
        alert_id=alert_id,
        from_status=current_status,
        to_status=ALERT_STATUS_RESOLVED,
        changed_by=user_id,
        note=resolution_note,
        changed_at=now,
    )

    logger.info(
        "Alert resolved",
        extra={"alert_id": alert_id, "user_id": user_id, "store_id": store_id},
    )
    return _to_resolve_response(_firestore_to_response(updated))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetch_and_validate_alert(alert_id: str, store_id: str) -> dict[str, Any]:
    """
    Fetch an alert and confirm it belongs to the given store.

    Raises NotFoundError if the alert does not exist or is scoped to a different store.
    """
    alert = await repository.get_alert_by_id(alert_id)
    if alert is None or alert.get("store_id") != store_id:
        raise AlertNotFoundError(
            f"Alert '{alert_id}' not found.",
            details={"alert_id": alert_id},
        )
    return alert


def _validate_transition(alert_id: str, from_status: str, to_status: str) -> None:
    """
    Check that the requested lifecycle transition is allowed.

    Raises ConflictError with code INVALID_ALERT_TRANSITION if not.
    """
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidAlertTransitionError(
            f"Cannot transition alert from '{from_status}' to '{to_status}'.",
            details={
                "alert_id": alert_id,
                "current_status": from_status,
                "requested_status": to_status,
            },
        )


async def _write_event(
    alert_id: str,
    from_status: str,
    to_status: str,
    changed_by: str,
    note: Optional[str],
    changed_at: datetime,
) -> None:
    """Write an immutable event record to alerts/{alert_id}/events."""
    event_id = f"evt_{uuid.uuid4().hex}"
    event_data: dict[str, Any] = {
        "event_id": event_id,
        "from_status": from_status,
        "to_status": to_status,
        "changed_by": changed_by,
        "note": note,
        "changed_at": changed_at,
    }
    await repository.write_alert_event(alert_id, event_id, event_data)
