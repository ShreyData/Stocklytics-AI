"""
Data Pipeline Module – BigQuery Raw Loader.

Reads changed Firestore documents within a checkpoint window and
upserts them into the five BigQuery raw tables:

    stocklytics_raw.transactions_raw
    stocklytics_raw.transaction_items_raw
    stocklytics_raw.inventory_snapshot_raw
    stocklytics_raw.customers_raw
    stocklytics_raw.alerts_raw

Table schemas match database_design.md §4 exactly.

Idempotency:
    Each table uses BigQuery MERGE (upsert) on its natural key so that
    reprocessing the same checkpoint window does not create duplicate rows
    (data_pipeline_design.md §10, data_pipeline_implementation.md §9).

Source collections read (Firestore, database_design.md §3):
    - transactions   (created_at >= checkpoint_start)
    - products       (updated_at >= checkpoint_start) → inventory_snapshot_raw
    - customers      (updated_at >= checkpoint_start)
    - alerts         (created_at / last_evaluated_at / acknowledged_at / resolved_at in window)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import io
import json

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


async def _query_firestore_window(
    db: firestore.AsyncClient,
    *,
    collection: str,
    store_id: str,
    since: datetime,
    until: datetime,
    timestamp_field: str = "updated_at",
) -> list[dict]:
    """Return all documents in `collection` for `store_id` updated between `since` and `until`."""
    query = (
        db.collection(collection)
        .where("store_id", "==", store_id)
        .where(timestamp_field, ">=", since)
        .where(timestamp_field, "<", until)
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
    merge_keys: str | list[str],
) -> None:
    """
    Perform an idempotent BigQuery MERGE.
    Loads rows into a temporary table, then runs a MERGE statement to upsert.
    """
    if not rows:
        return

    key_columns = [merge_keys] if isinstance(merge_keys, str) else merge_keys
    full_table = f"{project}.{dataset}.{table}"
    temp_table_id = f"{project}.{dataset}.{table}_temp_{uuid.uuid4().hex[:8]}"

    # 1. Load rows into temp table
    buf = io.StringIO()
    for row in rows:
        buf.write(json.dumps(row) + "\n")
    buf.seek(0)
    
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=True,
    )
    load_job = bq.load_table_from_file(buf, temp_table_id, job_config=job_config)
    load_job.result()  # Wait for load

    try:
        # 2. Execute MERGE
        columns = list(rows[0].keys())
        set_clause = ", ".join(f"T.{col} = S.{col}" for col in columns if col not in key_columns)
        insert_cols = ", ".join(columns)
        insert_vals = ", ".join(f"S.{col}" for col in columns)
        on_clause = " AND ".join(f"T.{col} = S.{col}" for col in key_columns)

        sql = f"""
        MERGE `{full_table}` AS T
        USING `{temp_table_id}` AS S
        ON {on_clause}
        WHEN MATCHED THEN
            UPDATE SET {set_clause}
        WHEN NOT MATCHED THEN
            INSERT ({insert_cols}) VALUES ({insert_vals})
        """
        bq.query(sql).result()
    finally:
        # 3. Cleanup temp table
        bq.delete_table(temp_table_id, not_found_ok=True)


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
    txns = await _query_firestore_window(
        db,
        collection="transactions",
        store_id=store_id,
        since=checkpoint_start,
        until=checkpoint_end,
        timestamp_field="created_at",
    )

    project = _settings.bigquery_project_id
    dataset = _settings.bigquery_dataset_raw

    txn_rows = []
    item_rows = []

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
        txn_store_id = _safe_str(txn.get("store_id"))

        # Enforce one row per (transaction_id, product_id) so MERGE stays deterministic.
        aggregated_items: dict[str, dict[str, Any]] = {}
        for item in txn.get("items", []):
            product_id = _safe_str(item.get("product_id"))
            if not product_id:
                continue

            quantity = _safe_int(item.get("quantity")) or 0
            line_total = _safe_float(item.get("line_total")) or 0.0
            unit_price = _safe_float(item.get("unit_price"))
            product_name = _safe_str(item.get("product_name"))

            current = aggregated_items.get(product_id)
            if current is None:
                aggregated_items[product_id] = {
                    "transaction_id": txn_id,
                    "store_id": txn_store_id,
                    "product_id": product_id,
                    "product_name": product_name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "sale_timestamp": _ts(txn.get("sale_timestamp")),
                }
                continue

            current["quantity"] = int(current.get("quantity", 0)) + quantity
            current["line_total"] = round(float(current.get("line_total", 0.0)) + line_total, 2)
            if current.get("product_name") is None and product_name is not None:
                current["product_name"] = product_name
            if current.get("unit_price") is None and unit_price is not None:
                current["unit_price"] = unit_price

        item_rows.extend(aggregated_items.values())

    _merge_query(bq, project=project, dataset=dataset, table="transactions_raw", rows=txn_rows, merge_keys="transaction_id")
    _merge_query(
        bq,
        project=project,
        dataset=dataset,
        table="transaction_items_raw",
        rows=item_rows,
        merge_keys=["transaction_id", "product_id"],
    )

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
    products = await _query_firestore_window(
        db,
        collection="products",
        store_id=store_id,
        since=checkpoint_start,
        until=checkpoint_end,
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

    _merge_query(bq, project=project, dataset=dataset, table="inventory_snapshot_raw", rows=rows, merge_keys="snapshot_id")

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
    customers = await _query_firestore_window(
        db,
        collection="customers",
        store_id=store_id,
        since=checkpoint_start,
        until=checkpoint_end,
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

    _merge_query(bq, project=project, dataset=dataset, table="customers_raw", rows=rows, merge_keys="customer_id")

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
    alerts_by_doc_id: dict[str, dict[str, Any]] = {}
    for timestamp_field in ("created_at", "last_evaluated_at", "acknowledged_at", "resolved_at"):
        changed = await _query_firestore_window(
            db,
            collection="alerts",
            store_id=store_id,
            since=checkpoint_start,
            until=checkpoint_end,
            timestamp_field=timestamp_field,
        )
        for alert in changed:
            doc_id = str(alert.get("_doc_id", ""))
            if doc_id:
                alerts_by_doc_id[doc_id] = alert

    alerts = list(alerts_by_doc_id.values())

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

    _merge_query(bq, project=project, dataset=dataset, table="alerts_raw", rows=rows, merge_keys="alert_id")

    logger.info(
        "Loaded alerts raw",
        extra={"store_id": store_id, "alerts": len(rows)},
    )
    return len(alerts), len(rows)
