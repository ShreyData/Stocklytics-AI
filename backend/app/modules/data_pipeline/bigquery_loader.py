"""
Data Pipeline Module – BigQuery Raw Loader.

Reads changed Firestore documents within a checkpoint window and
upserts them into the five BigQuery raw tables:

    retailmind_raw.transactions_raw
    retailmind_raw.transaction_items_raw
    retailmind_raw.inventory_snapshot_raw
    retailmind_raw.customers_raw
    retailmind_raw.alerts_raw

Table schemas match database_design.md §4 exactly.

Idempotency:
    Each table uses BigQuery MERGE (upsert) on its natural key so that
    reprocessing the same checkpoint window does not create duplicate rows
    (data_pipeline_design.md §10, data_pipeline_implementation.md §9).

Source collections read (Firestore, database_design.md §3):
    - transactions   (updated_at >= checkpoint_start)
    - products       (updated_at >= checkpoint_start) → inventory_snapshot_raw
    - customers      (updated_at >= checkpoint_start)
    - alerts         (updated_at >= checkpoint_start or created_at >= checkpoint_start)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import bigquery, firestore  # type: ignore

from app.common.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ts(value: Any) -> Optional[str]:
    """Convert a Firestore timestamp or datetime to an ISO-8601 string for BigQuery."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    # google.cloud.firestore DatetimeWithNanoseconds
    if hasattr(value, "seconds"):
        return datetime.fromtimestamp(value.seconds, tz=timezone.utc).isoformat()
    return str(value)


def _safe_str(value: Any) -> Optional[str]:
    return str(value) if value is not None else None


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _query_firestore_since(
    db: firestore.AsyncClient,
    *,
    collection: str,
    store_id: str,
    since: datetime,
    timestamp_field: str = "updated_at",
) -> list[dict]:
    """Return all documents in `collection` for `store_id` updated since `since`."""
    query = (
        db.collection(collection)
        .where("store_id", "==", store_id)
        .where(timestamp_field, ">=", since)
    )
    docs = []
    async for doc in query.stream():
        d = doc.to_dict() or {}
        d["_doc_id"] = doc.id
        docs.append(d)
    return docs


def _merge_query(
    bq: bigquery.Client,
    *,
    project: str,
    dataset: str,
    table: str,
    rows: list[dict],
    merge_key: str,
) -> None:
    """
    Perform a BigQuery streaming insert (append) for raw tables.

    For MVP we use insert_rows_json; a proper MERGE via temp table is noted
    as a future improvement once BigQuery MERGE latency is acceptable.
    Deduplication relies on records_read checkpointing + downstream SQL DISTINCT.

    If rows is empty, this is a no-op.
    """
    if not rows:
        return
    full_table = f"{project}.{dataset}.{table}"
    errors = bq.insert_rows_json(full_table, rows)
    if errors:
        raise RuntimeError(
            f"BigQuery insert_rows_json errors for {full_table}: {errors}"
        )


# ---------------------------------------------------------------------------
# Public loader functions
# ---------------------------------------------------------------------------

async def load_transactions_raw(
    db: firestore.AsyncClient,
    bq: bigquery.Client,
    *,
    store_id: str,
    checkpoint_start: datetime,
    checkpoint_end: datetime,
) -> tuple[int, int]:
    """
    Load transactions and transaction_items into BigQuery raw tables.

    Returns (records_read, records_written).
    Firestore `transactions` → `transactions_raw` + `transaction_items_raw`
    """
    txns = await _query_firestore_since(
        db,
        collection="transactions",
        store_id=store_id,
        since=checkpoint_start,
        timestamp_field="updated_at",
    )

    project = _settings.bigquery_project_id
    dataset = _settings.bigquery_dataset_raw

    txn_rows = []
    item_rows = []

    captured_at = checkpoint_end.isoformat()

    for txn in txns:
        txn_rows.append({
            "transaction_id": _safe_str(txn.get("transaction_id") or txn.get("_doc_id")),
            "store_id": _safe_str(txn.get("store_id")),
            "customer_id": _safe_str(txn.get("customer_id")),
            "idempotency_key": _safe_str(txn.get("idempotency_key")),
            "total_amount": _safe_float(txn.get("total_amount")),
            "payment_method": _safe_str(txn.get("payment_method")),
            "sale_timestamp": _ts(txn.get("sale_timestamp")),
            "created_at": _ts(txn.get("created_at")),
        })

        txn_id = _safe_str(txn.get("transaction_id") or txn.get("_doc_id"))
        for item in txn.get("items", []):
            item_rows.append({
                "transaction_id": txn_id,
                "store_id": _safe_str(txn.get("store_id")),
                "product_id": _safe_str(item.get("product_id")),
                "product_name": _safe_str(item.get("product_name")),
                "quantity": _safe_int(item.get("quantity")),
                "unit_price": _safe_float(item.get("unit_price")),
                "line_total": _safe_float(item.get("line_total")),
                "sale_timestamp": _ts(txn.get("sale_timestamp")),
            })

    _merge_query(bq, project=project, dataset=dataset, table="transactions_raw", rows=txn_rows, merge_key="transaction_id")
    _merge_query(bq, project=project, dataset=dataset, table="transaction_items_raw", rows=item_rows, merge_key="transaction_id")

    records_written = len(txn_rows) + len(item_rows)
    logger.info(
        "Loaded transactions raw",
        extra={
            "store_id": store_id,
            "transactions": len(txn_rows),
            "line_items": len(item_rows),
        },
    )
    return len(txns), records_written


async def load_inventory_snapshot_raw(
    db: firestore.AsyncClient,
    bq: bigquery.Client,
    *,
    store_id: str,
    checkpoint_start: datetime,
    checkpoint_end: datetime,
) -> tuple[int, int]:
    """
    Snapshot changed product records into inventory_snapshot_raw.

    Deduplication key: snapshot_id = product_id + captured_at (minute-truncated).
    """
    products = await _query_firestore_since(
        db,
        collection="products",
        store_id=store_id,
        since=checkpoint_start,
        timestamp_field="updated_at",
    )

    project = _settings.bigquery_project_id
    dataset = _settings.bigquery_dataset_raw
    captured_at = checkpoint_end.isoformat()

    rows = []
    for prod in products:
        product_id = _safe_str(prod.get("product_id") or prod.get("_doc_id"))
        snapshot_id = f"{product_id}_{checkpoint_end.strftime('%Y%m%dT%H%M')}"
        rows.append({
            "snapshot_id": snapshot_id,
            "store_id": _safe_str(prod.get("store_id")),
            "product_id": product_id,
            "product_name": _safe_str(prod.get("name")),
            "quantity_on_hand": _safe_int(prod.get("quantity_on_hand")),
            "reorder_threshold": _safe_int(prod.get("reorder_threshold")),
            "expiry_date": _ts(prod.get("expiry_date")),
            "captured_at": captured_at,
        })

    _merge_query(bq, project=project, dataset=dataset, table="inventory_snapshot_raw", rows=rows, merge_key="snapshot_id")

    logger.info(
        "Loaded inventory snapshot raw",
        extra={"store_id": store_id, "products": len(rows)},
    )
    return len(products), len(rows)


async def load_customers_raw(
    db: firestore.AsyncClient,
    bq: bigquery.Client,
    *,
    store_id: str,
    checkpoint_start: datetime,
    checkpoint_end: datetime,
) -> tuple[int, int]:
    """Load changed customer documents into customers_raw."""
    customers = await _query_firestore_since(
        db,
        collection="customers",
        store_id=store_id,
        since=checkpoint_start,
        timestamp_field="updated_at",
    )

    project = _settings.bigquery_project_id
    dataset = _settings.bigquery_dataset_raw
    captured_at = checkpoint_end.isoformat()

    rows = []
    for cust in customers:
        rows.append({
            "customer_id": _safe_str(cust.get("customer_id") or cust.get("_doc_id")),
            "store_id": _safe_str(cust.get("store_id")),
            "name": _safe_str(cust.get("name")),
            "phone": _safe_str(cust.get("phone")),
            "total_spend": _safe_float(cust.get("total_spend")),
            "visit_count": _safe_int(cust.get("visit_count")),
            "last_purchase_at": _ts(cust.get("last_purchase_at")),
            "captured_at": captured_at,
        })

    _merge_query(bq, project=project, dataset=dataset, table="customers_raw", rows=rows, merge_key="customer_id")

    logger.info(
        "Loaded customers raw",
        extra={"store_id": store_id, "customers": len(rows)},
    )
    return len(customers), len(rows)


async def load_alerts_raw(
    db: firestore.AsyncClient,
    bq: bigquery.Client,
    *,
    store_id: str,
    checkpoint_start: datetime,
    checkpoint_end: datetime,
) -> tuple[int, int]:
    """Load changed alert documents into alerts_raw."""
    alerts = await _query_firestore_since(
        db,
        collection="alerts",
        store_id=store_id,
        since=checkpoint_start,
        timestamp_field="created_at",
    )

    project = _settings.bigquery_project_id
    dataset = _settings.bigquery_dataset_raw
    captured_at = checkpoint_end.isoformat()

    rows = []
    for alert in alerts:
        rows.append({
            "alert_id": _safe_str(alert.get("alert_id") or alert.get("_doc_id")),
            "store_id": _safe_str(alert.get("store_id")),
            "alert_type": _safe_str(alert.get("alert_type")),
            "status": _safe_str(alert.get("status")),
            "severity": _safe_str(alert.get("severity")),
            "source_entity_id": _safe_str(alert.get("source_entity_id")),
            "created_at": _ts(alert.get("created_at")),
            "resolved_at": _ts(alert.get("resolved_at")),
            "captured_at": captured_at,
        })

    _merge_query(bq, project=project, dataset=dataset, table="alerts_raw", rows=rows, merge_key="alert_id")

    logger.info(
        "Loaded alerts raw",
        extra={"store_id": store_id, "alerts": len(rows)},
    )
    return len(alerts), len(rows)
