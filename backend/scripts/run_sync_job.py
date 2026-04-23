#!/usr/bin/env python3
"""
Cloud Run Job Entrypoint: pipeline-sync-job

Triggered by Cloud Scheduler every 15 minutes.
Iterates over active stores and runs the incremental sync (Firestore -> BQ Raw).
Does NOT run mart transforms.

Usage:
    python -m scripts.run_sync_job
"""

import asyncio
import logging
import sys

from google.cloud import bigquery
from google.cloud import firestore

from app.common.config import setup_logging, get_settings
from app.modules.data_pipeline import sync_runner

logger = logging.getLogger(__name__)


async def _get_active_store_ids(db: firestore.AsyncClient) -> list[str]:
    """Fetch stores from Firestore. Adjust query based on tenant model."""
    # For MVP, assume all stores in the 'stores' collection are active
    stores = []
    async for doc in db.collection("stores").stream():
        stores.append(doc.id)
    return stores


async def main() -> None:
    setup_logging()
    _settings = get_settings()
    
    db = firestore.AsyncClient(project=_settings.firestore_project_id or None)
    bq = bigquery.Client(project=_settings.bigquery_project_id or None)

    logger.info("Starting pipeline-sync-job")

    try:
        stores = await _get_active_store_ids(db)
        logger.info(f"Found {len(stores)} active stores for sync")

        for store_id in stores:
            try:
                # Fire-and-forget sync for each store sequentially
                # In a larger system, we might use asyncio.gather or pub/sub fanout
                run_id = await sync_runner.run_incremental_sync(db, bq, store_id=store_id)
                logger.info(f"Sync complete for store {store_id}, run_id={run_id}")
            except Exception as e:
                logger.error(f"Uncaught exception syncing store {store_id}", exc_info=e)
                # Continue with other stores

    except Exception as e:
        logger.error("Failed to list active stores", exc_info=e)
        sys.exit(1)

    logger.info("pipeline-sync-job complete")


if __name__ == "__main__":
    asyncio.run(main())
