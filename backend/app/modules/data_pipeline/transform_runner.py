"""
Data Pipeline Module – Transform Runner.

Orchestrates Step 2 of the pipeline (data_pipeline_design.md §3, Steps 3–4):

    1. Create pipeline_run record (MART_REFRESH type)
    2. Run all mart transforms via mart_transform.run_all_mart_transforms
    3. On success:
        - Mark run SUCCEEDED
        - Write analytics_metadata.analytics_last_updated_at  ← ONLY on success
    4. On failure:
        - Retry up to 3 times
        - Mark run FAILED, write pipeline_failures
        - analytics_last_updated_at is NOT updated
        - Existing mart tables stay available (stale reads)

Rule (shared_business_rules.md §10, data_pipeline_design.md §8):
    analytics_last_updated_at MUST NOT advance on a failed mart refresh.
    Frontend and AI see older freshness and communicate stale data clearly.

This runner is invoked by:
    - scripts/run_transform_job.py  (Cloud Run Job, scheduled after sync)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from google.cloud import bigquery, firestore  # type: ignore

from app.modules.data_pipeline import mart_transform, repository
from app.modules.data_pipeline.failure_handler import run_with_retry
from app.modules.data_pipeline.schemas import (
    PIPELINE_RUN_TYPE_MART_REFRESH,
    PIPELINE_RUN_STATUS_RUNNING,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def run_mart_refresh(
    db: firestore.AsyncClient,
    bq: bigquery.Client,
    *,
    store_id: str,
    source_window_start: datetime,
    source_window_end: datetime,
) -> str:
    """
    Execute the full mart refresh for one store.

    Returns the pipeline_run_id.

    Parameters:
        source_window_start / source_window_end:
            The checkpoint window from the preceding sync run.
            Stored in pipeline_runs for traceability.
    """
    pipeline_run_id = await repository.create_pipeline_run(
        db,
        store_id=store_id,
        run_type=PIPELINE_RUN_TYPE_MART_REFRESH,
        checkpoint_start=source_window_start,
        checkpoint_end=source_window_end,
    )

    logger.info(
        "Transform runner started",
        extra={
            "pipeline_run_id": pipeline_run_id,
            "store_id": store_id,
        },
    )

    # The analytics_last_updated_at stamped into mart rows is fixed at the
    # moment the transform begins so that all mart rows share the same value.
    analytics_ts = _utcnow()

    def _transform_all() -> None:
        """Synchronous wrapper so BigQuery DML can run in the thread pool."""
        mart_transform.run_all_mart_transforms(
            bq,
            store_id=store_id,
            analytics_last_updated_at=analytics_ts,
        )

    async def _async_transform() -> None:
        # Run blocking BQ DML in a thread pool to avoid blocking the event loop.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _transform_all)

    await repository.update_pipeline_run_running(
        db, pipeline_run_id=pipeline_run_id, attempt_count=1
    )

    success, attempt_count, error_message = await run_with_retry(
        _async_transform,
        stage_name="MART_REFRESH",
        pipeline_run_id=pipeline_run_id,
    )

    if success:
        await repository.mark_pipeline_run_succeeded(
            db,
            pipeline_run_id=pipeline_run_id,
            records_read=0,   # transform does not count source rows
            records_written=0,
            checkpoint_end=source_window_end,
        )
        # ── CRITICAL: update analytics_last_updated_at only here, after success ──
        await repository.update_analytics_metadata(
            db,
            store_id=store_id,
            pipeline_run_id=pipeline_run_id,
            source_window_start=source_window_start,
            source_window_end=source_window_end,
        )
        logger.info(
            "Transform runner completed successfully",
            extra={"pipeline_run_id": pipeline_run_id, "store_id": store_id},
        )
    else:
        # Existing mart rows remain; analytics_last_updated_at is NOT updated.
        await repository.mark_pipeline_run_failed(
            db,
            pipeline_run_id=pipeline_run_id,
            attempt_count=attempt_count,
            failure_stage="MART_REFRESH",
            error_message=error_message,
        )
        await repository.write_pipeline_failure(
            db,
            pipeline_run_id=pipeline_run_id,
            store_id=store_id,
            source_module="Billing",
            batch_ref=f"{source_window_start.isoformat()}/{source_window_end.isoformat()}",
            retry_count=attempt_count,
            failure_stage="MART_REFRESH",
            error_message=error_message,
        )
        logger.warning(
            "Transform runner failed – analytics_last_updated_at NOT advanced",
            extra={
                "pipeline_run_id": pipeline_run_id,
                "store_id": store_id,
                "error": error_message,
            },
        )

    return pipeline_run_id
