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
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(".env")

from app.common.config import setup_logging, get_settings
from app.common.google_clients import create_bigquery_client, create_firestore_async_client, get_default_gcp_project
from app.modules.data_pipeline import transform_runner, repository
from app.modules.data_pipeline.schemas import (
    PIPELINE_RUN_TYPE_INCREMENTAL_SYNC,
    PIPELINE_RUN_TYPE_MART_REFRESH,
)

logger = logging.getLogger(__name__)


async def _get_active_store_ids(db) -> list[str]:
    stores = []
    async for doc in db.collection("stores").stream():
        stores.append(doc.id)
    return stores


def _to_utc_datetime(value):
    if hasattr(value, "seconds"):
        return datetime.fromtimestamp(value.seconds, tz=timezone.utc)
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return None


async def main() -> None:
    setup_logging()
    _settings = get_settings()
    
    db = create_firestore_async_client(project=_settings.firestore_project_id or None)
    bq = create_bigquery_client(project=get_default_gcp_project(_settings))

    logger.info("Starting pipeline-transform-job")

    try:
        stores = await _get_active_store_ids(db)
        logger.info(f"Found {len(stores)} active stores for transform")

        for store_id in stores:
            try:
                # Transforms must be sourced from a successful incremental sync run.
                last_sync_run = await repository.get_last_successful_run(
                    db,
                    store_id=store_id,
                    run_type=PIPELINE_RUN_TYPE_INCREMENTAL_SYNC,
                )
                if not last_sync_run or not last_sync_run.get("checkpoint_end"):
                    logger.warning(f"No successful sync run found for store {store_id}, skipping transform")
                    continue

                checkpoint_end = _to_utc_datetime(last_sync_run.get("checkpoint_end"))
                if checkpoint_end is None:
                    logger.warning(f"Invalid checkpoint type for store {store_id}, skipping")
                    continue

                checkpoint_start = _to_utc_datetime(last_sync_run.get("checkpoint_start"))
                if checkpoint_start is None:
                    checkpoint_start = datetime.now(tz=timezone.utc)

                # Avoid re-running transform for the same source window repeatedly.
                last_transform_run = await repository.get_last_successful_run(
                    db,
                    store_id=store_id,
                    run_type=PIPELINE_RUN_TYPE_MART_REFRESH,
                )
                transformed_end = _to_utc_datetime(
                    (last_transform_run or {}).get("checkpoint_end")
                )
                if transformed_end is not None and transformed_end >= checkpoint_end:
                    logger.info(
                        "No new successful sync window to transform; skipping",
                        extra={"store_id": store_id, "checkpoint_end": checkpoint_end.isoformat()},
                    )
                    continue

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
