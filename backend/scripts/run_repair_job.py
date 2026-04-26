#!/usr/bin/env python3
"""
Cloud Run Job Entrypoint: pipeline-repair-job

Triggered nightly by Cloud Scheduler.
Finds all OPEN pipeline failures (dead letters) and attempts to reprocess them.

Usage:
    python -m scripts.run_repair_job
"""

import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv(".env")

from app.common.config import setup_logging, get_settings
from app.common.google_clients import create_bigquery_client, create_firestore_async_client, get_default_gcp_project
from app.modules.data_pipeline import repair_runner

logger = logging.getLogger(__name__)


async def _get_active_store_ids(db) -> list[str]:
    stores = []
    async for doc in db.collection("stores").stream():
        stores.append(doc.id)
    return stores


async def main() -> None:
    setup_logging()
    _settings = get_settings()
    
    db = create_firestore_async_client(project=_settings.firestore_project_id or None)
    bq = create_bigquery_client(project=get_default_gcp_project(_settings))

    logger.info("Starting pipeline-repair-job")

    try:
        stores = await _get_active_store_ids(db)
        logger.info(f"Found {len(stores)} active stores for repair check")

        for store_id in stores:
            try:
                results = await repair_runner.run_repair(db, bq, store_id=store_id)
                if results["recovered"] > 0 or results["failed"] > 0:
                    logger.info(
                        f"Repair summary for store {store_id}",
                        extra={"repair_results": results}
                    )
            except Exception as e:
                logger.error(f"Uncaught exception repairing store {store_id}", exc_info=e)

    except Exception as e:
        logger.error("Failed to list active stores", exc_info=e)
        sys.exit(1)

    logger.info("pipeline-repair-job complete")


if __name__ == "__main__":
    asyncio.run(main())
