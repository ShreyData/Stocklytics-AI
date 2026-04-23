"""
Data Pipeline Module – Repair Runner.

Nightly job that reprocesses failed checkpoint windows.

Responsibilities (data_pipeline_design.md §12, §10):
    1. Query pipeline_failures with dead_letter_status = OPEN.
    2. For each open failure:
        a. Mark failure as REPROCESSING.
        b. Re-run the sync for the failed window.
        c. Re-run the mart transform.
        d. If recovery succeeds → mark failure RECOVERED.
        e. If recovery fails   → leave status REPROCESSING (manual attention needed).

Rule:
    analytics_last_updated_at is updated only inside transform_runner
    after confirmed mart success. This runner does not touch it directly.

Invoked by: scripts/run_repair_job.py (nightly Cloud Run Job).
"""

from __future__ import annotations

import logging

from google.cloud import bigquery, firestore  # type: ignore

from app.modules.data_pipeline import repository, sync_runner, transform_runner
from app.modules.data_pipeline.checkpoint_manager import get_checkpoint_window

logger = logging.getLogger(__name__)


async def run_repair(
    db: firestore.AsyncClient,
    bq: bigquery.Client,
    *,
    store_id: str,
) -> dict:
    """
    Reprocess all OPEN pipeline failures for the given store.

    Returns a summary dict: {recovered: int, failed: int}.
    """
    open_failures = await repository.list_pipeline_failures(db, store_id=store_id, limit=20)

    recovered = 0
    still_failed = 0

    for failure in open_failures:
        failure_id = failure.get("failure_id", "")
        pipeline_run_id = failure.get("pipeline_run_id", "")

        logger.info(
            "Repair: attempting recovery",
            extra={"failure_id": failure_id, "pipeline_run_id": pipeline_run_id},
        )

        await repository.mark_failure_reprocessing(db, failure_id=failure_id)

        try:
            # Re-run incremental sync from the current checkpoint window.
            # The checkpoint_manager finds the last successful run and resumes from there,
            # which covers the failed window if no successful run has happened since.
            new_sync_run_id = await sync_runner.run_incremental_sync(
                db, bq, store_id=store_id
            )

            # Retrieve the sync run to check success and get window bounds.
            sync_run_doc = await repository.get_pipeline_run(
                db, pipeline_run_id=new_sync_run_id
            )

            if sync_run_doc and sync_run_doc.get("status") == "SUCCEEDED":
                checkpoint_start = sync_run_doc.get("checkpoint_start")
                checkpoint_end = sync_run_doc.get("checkpoint_end")

                # Re-run mart refresh.
                from datetime import datetime, timezone  # noqa: PLC0415

                def _to_dt(v):
                    if isinstance(v, datetime):
                        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
                    if hasattr(v, "seconds"):
                        return datetime.fromtimestamp(v.seconds, tz=timezone.utc)
                    return datetime.now(tz=timezone.utc)

                await transform_runner.run_mart_refresh(
                    db, bq,
                    store_id=store_id,
                    source_window_start=_to_dt(checkpoint_start),
                    source_window_end=_to_dt(checkpoint_end),
                )

                await repository.mark_failure_recovered(db, failure_id=failure_id)
                recovered += 1
                logger.info(
                    "Repair: failure recovered",
                    extra={"failure_id": failure_id},
                )
            else:
                still_failed += 1
                logger.warning(
                    "Repair: sync re-run did not succeed; leaving REPROCESSING",
                    extra={"failure_id": failure_id, "new_sync_run_id": new_sync_run_id},
                )

        except Exception as exc:  # noqa: BLE001
            still_failed += 1
            logger.error(
                "Repair: unexpected error during recovery",
                extra={"failure_id": failure_id, "error": str(exc)},
                exc_info=exc,
            )

    logger.info(
        "Repair run complete",
        extra={"store_id": store_id, "recovered": recovered, "still_failed": still_failed},
    )
    return {"recovered": recovered, "failed": still_failed}
