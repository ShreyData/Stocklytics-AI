#!/usr/bin/env python3
"""
Cloud Run Job Entrypoint: pipeline-transform-job

Triggered by Cloud Scheduler every 15 minutes, typically slightly offset
after pipeline-sync-job finishes.
Finds the last successful sync run and refreshes mart tables.

Usage:
    python -m scripts.run_transform_job
"""

import asyncio
import logging
import sys

from google.cloud import bigquery
from google.cloud import firestore

from app.common.config import setup_logging, get_settings
from app.modules.data_pipeline import transform_runner, repository

logger = logging.getLogger(__name__)


async def _get_active_store_ids(db: firestore.AsyncClient) -> list[str]:
    stores = []
    async for doc in db.collection("stores").stream():
        stores.append(doc.id)
    return stores


async def main() -> None:
    setup_logging()
    _settings = get_settings()
    
    db = firestore.AsyncClient(project=_settings.firestore_project_id or None)
    bq = bigquery.Client(project=_settings.bigquery_project_id or None)

    logger.info("Starting pipeline-transform-job")

    try:
        stores = await _get_active_store_ids(db)
        logger.info(f"Found {len(stores)} active stores for transform")

        for store_id in stores:
            try:
                # Resolve the source window by finding the last successful pipeline run.
                # In MVP, this relies on sync completing recently.
                last_run = await repository.get_last_successful_run(db, store_id=store_id)
                
                if not last_run or not last_run.get("checkpoint_end"):
                    logger.warning(f"No successful sync run found for store {store_id}, skipping transform")
                    continue
                
                # Firestore returns DatetimeWithNanoseconds for timestamps
                raw_end = last_run["checkpoint_end"]
                from datetime import datetime, timezone
                if hasattr(raw_end, "seconds"):
                    checkpoint_end = datetime.fromtimestamp(raw_end.seconds, tz=timezone.utc)
                elif isinstance(raw_end, datetime):
                    checkpoint_end = raw_end.replace(tzinfo=timezone.utc) if raw_end.tzinfo is None else raw_end
                else:
                    logger.warning(f"Invalid checkpoint type for store {store_id}, skipping")
                    continue

                # The start doesn't matter strictly for BigQuery mart refreshes (we refresh the whole day),
                # but we need it for metadata.
                raw_start = last_run.get("checkpoint_start")
                if hasattr(raw_start, "seconds"):
                    checkpoint_start = datetime.fromtimestamp(raw_start.seconds, tz=timezone.utc)
                elif isinstance(raw_start, datetime):
                    checkpoint_start = raw_start.replace(tzinfo=timezone.utc) if raw_start.tzinfo is None else raw_start
                else:
                    checkpoint_start = datetime.now(tz=timezone.utc)

                run_id = await transform_runner.run_mart_refresh(
                    db, bq,
                    store_id=store_id,
                    source_window_start=checkpoint_start,
                    source_window_end=checkpoint_end,
                )
                logger.info(f"Transform complete for store {store_id}, run_id={run_id}")
            except Exception as e:
                logger.error(f"Uncaught exception transforming store {store_id}", exc_info=e)

    except Exception as e:
        logger.error("Failed to list active stores", exc_info=e)
        sys.exit(1)

    logger.info("pipeline-transform-job complete")


if __name__ == "__main__":
    asyncio.run(main())
