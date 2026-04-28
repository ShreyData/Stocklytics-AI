#!/usr/bin/env python3
"""
Reset one store's operational, analytics, and AI data, then reseed one month.

This is an application-ops script only. It does not provision infra.

What it clears for the target store:
  - Firestore: products, customers, transactions, stock_adjustments, alerts,
    pipeline_runs, pipeline_failures, analytics_metadata, ai_chat_sessions
    and their nested messages
  - BigQuery raw tables: transactions_raw, transaction_items_raw,
    inventory_snapshot_raw, customers_raw, alerts_raw
  - BigQuery mart tables: sales_daily, product_sales_daily, customer_summary,
    inventory_health, dashboard_summary, product_embeddings

What it rebuilds:
  - one month of Firestore seed data
  - alerts from current seeded data
  - BigQuery raw + mart tables
  - product embeddings for RAG

Usage:
    python -m scripts.reset_and_seed_one_month_data --store-id store_001 --force
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

sys.path.insert(0, str(ROOT_DIR))

from app.common.config import get_settings, setup_logging
from app.common.google_clients import (
    create_bigquery_client,
    create_firestore_async_client,
    get_default_gcp_project,
)
from app.modules.alerts.engine import (
    evaluate_expiry_soon,
    evaluate_high_demand_for_store,
    evaluate_low_stock,
    evaluate_not_selling_for_store,
)
from app.modules.data_pipeline import sync_runner, transform_runner
from scripts.seed_one_month_data import seed

logger = logging.getLogger(__name__)

FIRESTORE_COLLECTIONS = (
    "products",
    "stock_adjustments",
    "transactions",
    "customers",
    "alerts",
    "pipeline_runs",
    "pipeline_failures",
)

BIGQUERY_RAW_TABLES = (
    "transactions_raw",
    "transaction_items_raw",
    "inventory_snapshot_raw",
    "customers_raw",
    "alerts_raw",
)

BIGQUERY_MART_TABLES = (
    "sales_daily",
    "product_sales_daily",
    "customer_summary",
    "inventory_health",
    "dashboard_summary",
    "product_embeddings",
)


async def _delete_store_docs(db, collection: str, store_id: str) -> int:
    deleted = 0
    async for doc in db.collection(collection).where("store_id", "==", store_id).stream():
        await doc.reference.delete()
        deleted += 1
    return deleted


async def _delete_chat_sessions(db, store_id: str) -> int:
    deleted = 0
    async for session_doc in db.collection("ai_chat_sessions").where("store_id", "==", store_id).stream():
        async for msg_doc in session_doc.reference.collection("messages").stream():
            await msg_doc.reference.delete()
        await session_doc.reference.delete()
        deleted += 1
    return deleted


async def _delete_analytics_metadata(db, store_id: str) -> int:
    deleted = 0
    metadata_doc = db.collection("analytics_metadata").document(f"{store_id}_dashboard")
    snapshot = await metadata_doc.get()
    if snapshot.exists:
        await metadata_doc.delete()
        deleted = 1
    return deleted


async def _ensure_store_document(db, store_id: str) -> None:
    now = datetime.now(timezone.utc)
    await db.collection("stores").document(store_id).set(
        {
            "store_id": store_id,
            "name": store_id,
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
        },
        merge=True,
    )


def _delete_bigquery_rows(bq, table_id: str, store_id: str) -> None:
    query = f"DELETE FROM `{table_id}` WHERE store_id = @store_id"
    from google.cloud import bigquery

    job = bq.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("store_id", "STRING", store_id)]
        ),
    )
    job.result()


def _table_exists(bq, table_id: str) -> bool:
    try:
        bq.get_table(table_id)
        return True
    except Exception:
        return False


async def _rebuild_alerts(db, store_id: str) -> None:
    async for doc in db.collection("products").where("store_id", "==", store_id).stream():
        product = doc.to_dict() or {}
        product.setdefault("product_id", doc.id)
        await evaluate_low_stock(
            store_id=store_id,
            product_id=str(product.get("product_id")),
            product_name=str(product.get("name", "Unknown Product")),
            current_stock=int(product.get("quantity_on_hand", 0) or 0),
            reorder_threshold=int(product.get("reorder_threshold", 0) or 0),
        )
        await evaluate_expiry_soon(
            store_id=store_id,
            product_id=str(product.get("product_id")),
            product_name=str(product.get("name", "Unknown Product")),
            expiry_date=product.get("expiry_date"),
            current_stock=int(product.get("quantity_on_hand", 0) or 0),
        )

    await evaluate_not_selling_for_store(store_id=store_id)
    await evaluate_high_demand_for_store(store_id=store_id)


async def main(store_id: str, force: bool) -> None:
    if not force:
        raise RuntimeError("Refusing to run without --force because this script deletes live store data.")

    setup_logging()
    settings = get_settings()
    db = create_firestore_async_client(project=settings.firestore_project_id or None)
    bq = create_bigquery_client(project=get_default_gcp_project(settings))

    logger.info("Resetting Firestore collections for store %s", store_id)
    for collection in FIRESTORE_COLLECTIONS:
        deleted = await _delete_store_docs(db, collection, store_id)
        logger.info("Deleted %s docs from %s", deleted, collection)

    chat_deleted = await _delete_chat_sessions(db, store_id)
    logger.info("Deleted %s AI chat sessions", chat_deleted)

    metadata_deleted = await _delete_analytics_metadata(db, store_id)
    logger.info("Deleted %s analytics metadata docs", metadata_deleted)

    logger.info("Resetting BigQuery rows for store %s", store_id)
    project = settings.bigquery_project_id
    if project:
        for table in BIGQUERY_RAW_TABLES:
            table_id = f"{project}.{settings.bigquery_dataset_raw}.{table}"
            if _table_exists(bq, table_id):
                await asyncio.to_thread(_delete_bigquery_rows, bq, table_id, store_id)
                logger.info("Cleared %s", table_id)
        for table in BIGQUERY_MART_TABLES:
            table_id = f"{project}.{settings.bigquery_dataset_mart}.{table}"
            if _table_exists(bq, table_id):
                await asyncio.to_thread(_delete_bigquery_rows, bq, table_id, store_id)
                logger.info("Cleared %s", table_id)
    else:
        logger.warning("BIGQUERY_PROJECT_ID not configured; skipping BigQuery cleanup and rebuild.")

    await _ensure_store_document(db, store_id)
    await seed(store_id=store_id, clear_existing=False)
    await _rebuild_alerts(db, store_id)

    if project:
        checkpoint_end = datetime.now(timezone.utc)
        checkpoint_start = checkpoint_end - timedelta(days=60)
        sync_run_id = await sync_runner.run_incremental_sync(
            db,
            bq,
            store_id=store_id,
            checkpoint_override=(checkpoint_start, checkpoint_end),
        )
        logger.info("Incremental sync rebuilt raw tables: %s", sync_run_id)

        transform_run_id = await transform_runner.run_mart_refresh(
            db,
            bq,
            store_id=store_id,
            source_window_start=checkpoint_start,
            source_window_end=checkpoint_end,
        )
        logger.info("Mart refresh rebuilt analytics and embeddings: %s", transform_run_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset one store and reseed one month of data.")
    parser.add_argument("--store-id", required=True, help="Target store ID to reset and rebuild.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Required acknowledgement because the script deletes existing store data.",
    )
    args = parser.parse_args()
    asyncio.run(main(store_id=args.store_id, force=args.force))
