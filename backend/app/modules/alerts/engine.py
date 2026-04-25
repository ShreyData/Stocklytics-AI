"""
Alerts Evaluation Engine.

Contains the logic for detecting urgent conditions and managing their lifecycles.
These functions can be invoked by hooks in other modules or by scheduled sweeps.
"""

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
    metadata: Optional[dict[str, Any]] = None,
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
            "metadata": metadata,
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
        "metadata": metadata,
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
    condition_key = f"LOW_STOCK_{product_id}"
    
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
            metadata={
                "quantity_on_hand": current_stock,
                "reorder_threshold": reorder_threshold,
            },
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
    condition_key = f"EXPIRY_SOON_{product_id}"
    
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
            metadata={
                "quantity_on_hand": current_stock,
                "expiry_date": expiry_date,
                "days_to_expiry": delta_days,
            },
        )
    else:
        await _resolve_if_exists(store_id, condition_key)


def _sum_units_sold_by_product(transactions: list[dict[str, Any]]) -> dict[str, int]:
    """
    Aggregate sold quantity per product_id from transaction item lines.
    """
    sold: dict[str, int] = defaultdict(int)
    for txn in transactions:
        if txn.get("status") and txn.get("status") != "COMPLETED":
            continue
        for item in txn.get("items", []):
            product_id = item.get("product_id")
            if not product_id:
                continue
            sold[product_id] += int(item.get("quantity", 0))
    return sold


async def evaluate_not_selling_for_store(
    store_id: str,
    lookback_days: int = 14,
) -> None:
    """
    Evaluate NOT_SELLING for all in-stock products in a store.

    Rule:
    - Trigger when quantity_on_hand > 0 and there are no sales in the last N days.
    - Resolve when product gets new sales or stock becomes 0.
    """
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(days=lookback_days)
    transactions = await repository.list_transactions_in_window(
        store_id=store_id,
        start_at=start_utc,
        end_at=now_utc,
    )
    sold_by_product = _sum_units_sold_by_product(transactions)

    products = await repository.list_products_for_store(store_id)
    for product in products:
        product_id = product.get("product_id")
        if not product_id:
            continue

        quantity_on_hand = int(product.get("quantity_on_hand", 0))
        condition_key = f"NOT_SELLING_{product_id}"

        if quantity_on_hand <= 0:
            await _resolve_if_exists(store_id, condition_key)
            continue

        sold_recently = sold_by_product.get(product_id, 0) > 0
        if sold_recently:
            await _resolve_if_exists(store_id, condition_key)
            continue

        product_name = product.get("name", "Unknown Product")
        await _create_or_update_alert(
            store_id=store_id,
            alert_type="NOT_SELLING",
            condition_key=condition_key,
            source_entity_id=product_id,
            severity="MEDIUM",
            title=f"{product_name} is not selling",
            message=f"No sales in the last {lookback_days} days while stock is still available.",
            metadata={
                "quantity_on_hand": quantity_on_hand,
                "lookback_days": lookback_days,
                "recent_sales_units": 0,
            },
        )


async def evaluate_high_demand_for_store(
    store_id: str,
    recent_days: int = 3,
    baseline_days: int = 14,
) -> None:
    """
    Evaluate HIGH_DEMAND for all products in a store.

    Rule:
    - Trigger if recent 3-day sales rate >= 1.5x previous baseline rate, OR
      stock cover is below 3 days.
    - Resolve when neither condition holds.
    """
    now_utc = datetime.now(timezone.utc)
    recent_start = now_utc - timedelta(days=recent_days)
    baseline_start = recent_start - timedelta(days=baseline_days)

    recent_txns = await repository.list_transactions_in_window(
        store_id=store_id,
        start_at=recent_start,
        end_at=now_utc,
    )
    baseline_txns = await repository.list_transactions_in_window(
        store_id=store_id,
        start_at=baseline_start,
        end_at=recent_start,
    )
    recent_sold = _sum_units_sold_by_product(recent_txns)
    baseline_sold = _sum_units_sold_by_product(baseline_txns)

    products = await repository.list_products_for_store(store_id)
    for product in products:
        product_id = product.get("product_id")
        if not product_id:
            continue

        quantity_on_hand = int(product.get("quantity_on_hand", 0))
        recent_units = recent_sold.get(product_id, 0)
        baseline_units = baseline_sold.get(product_id, 0)
        recent_rate = recent_units / float(recent_days)
        baseline_rate = baseline_units / float(baseline_days)
        stock_cover_days = (quantity_on_hand / recent_rate) if recent_rate > 0 else None

        high_growth = baseline_rate > 0 and recent_rate >= (1.5 * baseline_rate)
        low_stock_cover = stock_cover_days is not None and stock_cover_days < 3.0
        condition_key = f"HIGH_DEMAND_{product_id}"

        if not (high_growth or low_stock_cover):
            await _resolve_if_exists(store_id, condition_key)
            continue

        product_name = product.get("name", "Unknown Product")
        reason_text = "sales acceleration and low stock cover" if high_growth and low_stock_cover else (
            "sales acceleration vs baseline" if high_growth else "low stock cover"
        )
        await _create_or_update_alert(
            store_id=store_id,
            alert_type="HIGH_DEMAND",
            condition_key=condition_key,
            source_entity_id=product_id,
            severity="HIGH",
            title=f"{product_name} demand is high",
            message=f"Recent demand signal detected ({reason_text}).",
            metadata={
                "quantity_on_hand": quantity_on_hand,
                "recent_days": recent_days,
                "baseline_days": baseline_days,
                "recent_units_sold": recent_units,
                "baseline_units_sold": baseline_units,
                "recent_daily_rate": recent_rate,
                "baseline_daily_rate": baseline_rate,
                "stock_cover_days": stock_cover_days,
                "triggered_by_rate_spike": high_growth,
                "triggered_by_stock_cover": low_stock_cover,
            },
        )
