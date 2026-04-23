"""
Data Pipeline Module – Sync Runner.

Orchestrates Step 1 of the pipeline (data_pipeline_design.md §3, Step 2):

    1. Create pipeline_run record (QUEUED)
    2. Resolve checkpoint window from checkpoint_manager
    3. Load raw tables from Firestore into BigQuery (bigquery_loader)
    4. On success → mark run SUCCEEDED, advance checkpoint
    5. On failure → retry up to 3 times (failure_handler)
               → mark run FAILED, write pipeline_failures, keep checkpoint unchanged

This runner is invoked by:
    - service.trigger_sync()  (API-triggered)
    - scripts/run_sync_job.py (Cloud Run Job, scheduled)

It does NOT refresh mart tables – that is transform_runner's responsibility.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from google.cloud import bigquery, firestore  # type: ignore

from app.modules.data_pipeline import bigquery_loader, checkpoint_manager, repository
from app.modules.data_pipeline.failure_handler import run_with_retry
from app.modules.data_pipeline.schemas import (
    PIPELINE_RUN_TYPE_INCREMENTAL_SYNC,
    PIPELINE_RUN_STATUS_RUNNING,
)

logger = logging.getLogger(__name__)


async def run_incremental_sync(
    db: firestore.AsyncClient,
    bq: bigquery.Client,
    *,
    store_id: str,
    precreated_run_id: str | None = None,
    checkpoint_override: tuple[datetime, datetime] | None = None,
) -> str:
    """
    Execute the full incremental sync for one store.

    Returns the pipeline_run_id so the caller can track it.

    Failure semantics (data_pipeline_design.md §8, shared_business_rules.md §10):
        - If raw load fails after all retries, run is marked FAILED.
        - pipeline_failures is written with source_module context.
        - checkpoint is NOT advanced.
    """
    # 1. Resolve checkpoint window
    if checkpoint_override:
        checkpoint_start, checkpoint_end = checkpoint_override
    else:
        checkpoint_start, checkpoint_end = await checkpoint_manager.get_checkpoint_window(
            db, store_id=store_id
        )

    # 2. Create (or reuse) the pipeline_run record
    if precreated_run_id:
        pipeline_run_id = precreated_run_id
    else:
        pipeline_run_id = await repository.create_pipeline_run(
            db,
            store_id=store_id,
            run_type=PIPELINE_RUN_TYPE_INCREMENTAL_SYNC,
            checkpoint_start=checkpoint_start,
            checkpoint_end=checkpoint_end,
        )

    logger.info(
        "Sync runner started",
        extra={
            "pipeline_run_id": pipeline_run_id,
            "store_id": store_id,
            "checkpoint_start": checkpoint_start.isoformat(),
            "checkpoint_end": checkpoint_end.isoformat(),
        },
    )

    # 3. Run raw loads with retry
    total_read = 0
    total_written = 0

    async def _load_all() -> None:
        nonlocal total_read, total_written

        r1, w1 = await bigquery_loader.load_transactions_raw(
            db, bq,
            store_id=store_id,
            checkpoint_start=checkpoint_start,
            checkpoint_end=checkpoint_end,
        )
        r2, w2 = await bigquery_loader.load_inventory_snapshot_raw(
            db, bq,
            store_id=store_id,
            checkpoint_start=checkpoint_start,
            checkpoint_end=checkpoint_end,
        )
        r3, w3 = await bigquery_loader.load_customers_raw(
            db, bq,
            store_id=store_id,
            checkpoint_start=checkpoint_start,
            checkpoint_end=checkpoint_end,
        )
        r4, w4 = await bigquery_loader.load_alerts_raw(
            db, bq,
            store_id=store_id,
            checkpoint_start=checkpoint_start,
            checkpoint_end=checkpoint_end,
        )
        total_read += r1 + r2 + r3 + r4
        total_written += w1 + w2 + w3 + w4

    await repository.update_pipeline_run_running(
        db, pipeline_run_id=pipeline_run_id, attempt_count=1
    )

    success, attempt_count, error_message = await run_with_retry(
        _load_all,
        stage_name="LOAD_TO_BIGQUERY",
        pipeline_run_id=pipeline_run_id,
    )

    if success:
        # 4. Advance checkpoint only on success
        await repository.mark_pipeline_run_succeeded(
            db,
            pipeline_run_id=pipeline_run_id,
            records_read=total_read,
            records_written=total_written,
            checkpoint_end=checkpoint_end,
        )
        logger.info(
            "Sync runner completed successfully",
            extra={
                "pipeline_run_id": pipeline_run_id,
                "records_read": total_read,
                "records_written": total_written,
            },
        )
    else:
        # 5. Mark failed; do NOT advance checkpoint
        await repository.mark_pipeline_run_failed(
            db,
            pipeline_run_id=pipeline_run_id,
            attempt_count=attempt_count,
            failure_stage="LOAD_TO_BIGQUERY",
            error_message=error_message,
        )
        await repository.write_pipeline_failure(
            db,
            pipeline_run_id=pipeline_run_id,
            store_id=store_id,
            source_module="Billing",  # primary source for incremental sync
            batch_ref=f"{checkpoint_start.isoformat()}/{checkpoint_end.isoformat()}",
            retry_count=attempt_count,
            failure_stage="LOAD_TO_BIGQUERY",
            error_message=error_message,
        )

    return pipeline_run_id
