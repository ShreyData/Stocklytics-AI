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
        e. If recovery fails   → move status back to OPEN for safe retry.

Rule:
    analytics_last_updated_at is updated only inside transform_runner
    after confirmed mart success. This runner does not touch it directly.

Invoked by: scripts/run_repair_job.py (nightly Cloud Run Job).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from google.cloud import bigquery, firestore  # type: ignore

from app.modules.data_pipeline import repository, sync_runner, transform_runner

logger = logging.getLogger(__name__)


def _to_dt(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    if hasattr(value, "seconds"):
        return datetime.fromtimestamp(value.seconds, tz=timezone.utc)
    return None


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
        if not failure_id:
            still_failed += 1
            continue

        logger.info(
            "Repair: attempting recovery",
            extra={"failure_id": failure_id, "pipeline_run_id": pipeline_run_id},
        )

        await repository.mark_failure_reprocessing(db, failure_id=failure_id)

        try:
            # Parse batch_ref to get exact window to replay
            batch_ref = failure.get("batch_ref", "")
            override = None
            if "/" in batch_ref:
                try:
                    start_str, end_str = batch_ref.split("/", 1)
                    start_override = datetime.fromisoformat(start_str)
                    end_override = datetime.fromisoformat(end_str)
                    if start_override.tzinfo is None:
                        start_override = start_override.replace(tzinfo=timezone.utc)
                    if end_override.tzinfo is None:
                        end_override = end_override.replace(tzinfo=timezone.utc)
                    override = (start_override, end_override)
                except ValueError:
                    logger.warning("Could not parse batch_ref for repair", extra={"batch_ref": batch_ref})

            # Re-run incremental sync from the failed checkpoint window.
            new_sync_run_id = await sync_runner.run_incremental_sync(
                db, bq, store_id=store_id, checkpoint_override=override
            )

            # Retrieve the sync run to check success and get window bounds.
            sync_run_doc = await repository.get_pipeline_run(
                db, pipeline_run_id=new_sync_run_id
            )

            if sync_run_doc and sync_run_doc.get("status") == "SUCCEEDED":
                checkpoint_start = _to_dt(sync_run_doc.get("checkpoint_start"))
                checkpoint_end = _to_dt(sync_run_doc.get("checkpoint_end"))
                if checkpoint_start is None or checkpoint_end is None:
                    still_failed += 1
                    await repository.mark_failure_open(db, failure_id=failure_id)
                    logger.warning(
                        "Repair: checkpoint bounds missing after sync replay",
                        extra={"failure_id": failure_id, "new_sync_run_id": new_sync_run_id},
                    )
                    continue

                transform_run_id = await transform_runner.run_mart_refresh(
                    db, bq,
                    store_id=store_id,
                    source_window_start=checkpoint_start,
                    source_window_end=checkpoint_end,
                )

                transform_run_doc = await repository.get_pipeline_run(
                    db,
                    pipeline_run_id=transform_run_id,
                )
                if transform_run_doc and transform_run_doc.get("status") == "SUCCEEDED":
                    await repository.mark_failure_recovered(db, failure_id=failure_id)
                    recovered += 1
                    logger.info(
                        "Repair: failure recovered",
                        extra={"failure_id": failure_id},
                    )
                else:
                    still_failed += 1
                    await repository.mark_failure_open(db, failure_id=failure_id)
                    logger.warning(
                        "Repair: transform replay did not succeed",
                        extra={"failure_id": failure_id, "transform_run_id": transform_run_id},
                    )
            else:
                still_failed += 1
                await repository.mark_failure_open(db, failure_id=failure_id)
                logger.warning(
                    "Repair: sync re-run did not succeed; moved failure back to OPEN",
                    extra={"failure_id": failure_id, "new_sync_run_id": new_sync_run_id},
                )

        except Exception as exc:  # noqa: BLE001
            still_failed += 1
            try:
                await repository.mark_failure_open(db, failure_id=failure_id)
            except Exception:  # noqa: BLE001
                logger.exception("Repair: failed to reset dead_letter_status to OPEN", extra={"failure_id": failure_id})
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
