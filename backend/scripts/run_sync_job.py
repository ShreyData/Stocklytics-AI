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

from dotenv import load_dotenv

load_dotenv(".env")

from app.common.config import setup_logging, get_settings
from app.common.google_clients import create_bigquery_client, create_firestore_async_client, get_default_gcp_project
from app.modules.data_pipeline import repository, sync_runner

logger = logging.getLogger(__name__)


async def _get_active_store_ids(db) -> list[str]:
    """Fetch stores from Firestore. Adjust query based on tenant model."""
    # For MVP, assume all stores in the 'stores' collection are active
    stores = []
    async for doc in db.collection("stores").stream():
        stores.append(doc.id)
    return stores


async def main() -> None:
    setup_logging()
    _settings = get_settings()
    
    db = create_firestore_async_client(project=_settings.firestore_project_id or None)
    bq = create_bigquery_client(project=get_default_gcp_project(_settings))

    logger.info("Starting pipeline-sync-job")

    try:
        stores = await _get_active_store_ids(db)
        logger.info(f"Found {len(stores)} active stores for sync")

        for store_id in stores:
            try:
                active = await repository.get_active_run_for_store(db, store_id=store_id)
                if active:
                    logger.info(
                        "Skipping sync because a pipeline run is already active",
                        extra={
                            "store_id": store_id,
                            "active_pipeline_run_id": active.get("pipeline_run_id"),
                        },
                    )
                    continue

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
