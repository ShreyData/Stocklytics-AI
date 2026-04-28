#!/usr/bin/env python3
"""
Cloud Run Job Entrypoint (manual / one-shot): embedding-sync-job

Seeds or rebuilds product embeddings for all stores (or a single store).
Safe to run at any time — it replaces only the given store's rows in
product_embeddings and never touches mart tables or pipeline_run records.

Usage:
    python -m scripts.run_embedding_sync                  # all stores
    python -m scripts.run_embedding_sync --store-id abc   # one store

Scheduling:
    This script is intended as a manual trigger or a one-time bootstrap.
    Ongoing daily embedding updates are handled automatically inside
    transform_runner.run_mart_refresh() after each successful mart refresh.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv(".env")

from app.common.config import get_settings, setup_logging
from app.common.google_clients import (
    create_bigquery_client,
    create_firestore_async_client,
    get_default_gcp_project,
)
from app.modules.data_pipeline.embedding_sync import sync_product_embeddings

logger = logging.getLogger(__name__)


async def _list_store_ids(db) -> list[str]:
    """Return all store IDs from the Firestore stores collection."""
    store_ids: list[str] = []
    async for doc in db.collection("stores").stream():
        store_ids.append(doc.id)
    return store_ids


async def _fetch_products(db, store_id: str) -> list[dict[str, Any]]:
    """Fetch all products for a store from Firestore."""
    products: list[dict[str, Any]] = []
    async for doc in (
        db.collection("products").where("store_id", "==", store_id).stream()
    ):
        data = doc.to_dict() or {}
        data.setdefault("product_id", doc.id)
        products.append(data)
    return products


async def main(store_id_filter: str | None = None) -> None:
    setup_logging()
    settings = get_settings()

    db = create_firestore_async_client(project=settings.firestore_project_id or None)
    bq = create_bigquery_client(project=get_default_gcp_project(settings))

    if store_id_filter:
        store_ids = [store_id_filter]
        logger.info(f"Embedding sync: targeting single store '{store_id_filter}'")
    else:
        store_ids = await _list_store_ids(db)
        logger.info(f"Embedding sync: found {len(store_ids)} store(s)")

    if not store_ids:
        logger.warning("No stores found; nothing to embed.")
        return

    now = datetime.now(timezone.utc)
    total_embedded = 0
    failed_stores: list[str] = []

    for sid in store_ids:
        try:
            products = await _fetch_products(db, sid)
            logger.info(
                f"Embedding store={sid}: {len(products)} products",
            )
            count = await sync_product_embeddings(
                bq,
                store_id=sid,
                products=products,
                analytics_last_updated_at=now,
            )
            total_embedded += count
            logger.info(f"store={sid} done: embedded={count}")
        except Exception as exc:
            logger.error(f"Failed to embed store={sid}", exc_info=exc)
            failed_stores.append(sid)

    logger.info(
        f"Embedding sync complete: total_embedded={total_embedded}, "
        f"failed_stores={len(failed_stores)}"
    )
    if failed_stores:
        logger.error(f"Stores that failed: {failed_stores}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manually seed or rebuild product embeddings."
    )
    parser.add_argument(
        "--store-id",
        default=None,
        help="If provided, only sync embeddings for this store.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.store_id))
