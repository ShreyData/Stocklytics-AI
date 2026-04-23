"""
Alerts Evaluation Engine.

Contains the logic for detecting urgent conditions and managing their lifecycles.
These functions can be invoked by hooks in other modules or by scheduled sweeps.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.modules.alerts import repository
from app.modules.alerts.schemas import (
    ALERT_STATUS_ACTIVE,
    ALERT_STATUS_RESOLVED,
)
from app.modules.alerts.service import resolve_alert

logger = logging.getLogger(__name__)


async def _create_or_update_alert(
    store_id: str,
    alert_type: str,
    condition_key: str,
    source_entity_id: str,
    severity: str,
    title: str,
    message: str,
) -> dict[str, Any]:
    """Helper to upsert an alert based on condition key."""
    now = datetime.now(timezone.utc)
    existing_alert = await repository.get_alert_by_condition(store_id, condition_key)

    if existing_alert:
        # Update existing alert
        alert_id = existing_alert["alert_id"]
        updates = {
            "severity": severity,
            "title": title,
            "message": message,
            "last_evaluated_at": now,
        }
        updated = await repository.update_alert(alert_id, updates)
        return updated or existing_alert

    # Create new alert
    alert_id = f"alert_{uuid.uuid4().hex}"
    alert_data = {
        "alert_id": alert_id,
        "store_id": store_id,
        "alert_type": alert_type,
        "condition_key": condition_key,
        "source_entity_id": source_entity_id,
        "status": ALERT_STATUS_ACTIVE,
        "severity": severity,
        "title": title,
        "message": message,
        "created_at": now,
        "last_evaluated_at": now,
        "acknowledged_at": None,
        "acknowledged_by": None,
        "resolved_at": None,
        "resolved_by": None,
        "resolution_note": None,
    }
    
    created = await repository.create_alert(alert_id, alert_data)
    
    # Write creation event
    event_id = f"evt_{uuid.uuid4().hex}"
    await repository.write_alert_event(
        alert_id, 
        event_id, 
        {
            "event_id": event_id,
            "from_status": "NONE",
            "to_status": ALERT_STATUS_ACTIVE,
            "changed_by": "system",
            "note": "Alert triggered by evaluation engine.",
            "changed_at": now,
        }
    )
    return created


async def _resolve_if_exists(store_id: str, condition_key: str) -> None:
    """Helper to resolve an alert if it is currently open."""
    existing_alert = await repository.get_alert_by_condition(store_id, condition_key)
    if existing_alert:
        try:
            await resolve_alert(
                alert_id=existing_alert["alert_id"],
                store_id=store_id,
                user_id="system",
                resolution_note="Condition automatically cleared."
            )
        except Exception as e:
            logger.error(f"Failed to auto-resolve alert {existing_alert['alert_id']}: {e}")


async def evaluate_low_stock(
    store_id: str, 
    product_id: str, 
    product_name: str, 
    current_stock: int, 
    reorder_threshold: int
) -> None:
    """Evaluate low stock condition for a product."""
    condition_key = f"low_stock_{product_id}"
    
    if current_stock <= reorder_threshold:
        severity = "CRITICAL" if current_stock == 0 else "HIGH"
        title = f"{product_name} stock is low"
        message = f"Only {current_stock} units left. Reorder soon."
        await _create_or_update_alert(
            store_id=store_id,
            alert_type="LOW_STOCK",
            condition_key=condition_key,
            source_entity_id=product_id,
            severity=severity,
            title=title,
            message=message,
        )
    else:
        await _resolve_if_exists(store_id, condition_key)


async def evaluate_expiry_soon(
    store_id: str, 
    product_id: str, 
    product_name: str, 
    expiry_date: Optional[datetime], 
    current_stock: int
) -> None:
    """Evaluate expiry condition for a product."""
    condition_key = f"expiry_soon_{product_id}"
    
    if expiry_date is None or current_stock <= 0:
        await _resolve_if_exists(store_id, condition_key)
        return

    if expiry_date.tzinfo is None:
        expiry_date = expiry_date.replace(tzinfo=timezone.utc)
        
    now_utc = datetime.now(timezone.utc)
    delta_days = (expiry_date - now_utc).days
    
    if delta_days <= 7:
        severity = "HIGH" if delta_days <= 0 else "MEDIUM"
        title = f"{product_name} expires soon"
        
        if delta_days < 0:
            message = f"{current_stock} units have expired."
        elif delta_days == 0:
            message = f"{current_stock} units expire today."
        else:
            message = f"{current_stock} units expire within {delta_days} days."
            
        await _create_or_update_alert(
            store_id=store_id,
            alert_type="EXPIRY_SOON",
            condition_key=condition_key,
            source_entity_id=product_id,
            severity=severity,
            title=title,
            message=message,
        )
    else:
        await _resolve_if_exists(store_id, condition_key)
