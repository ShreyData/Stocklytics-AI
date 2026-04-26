"""
Data Pipeline Module – Checkpoint Manager.

Determines the time window for the next incremental sync run.

Rules (data_pipeline_design.md §10, shared_business_rules.md §10):
    - Resume from the last successful checkpoint_end.
    - If no prior successful run exists, start from a configured epoch
      (defaults to 30 days ago) so the first run back-fills recent data.
    - Checkpoint is NEVER advanced on a failed run.
      Only sync_runner / transform_runner call advance_checkpoint after
      confirmed success, through repository.mark_pipeline_run_succeeded.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.cloud import firestore  # type: ignore

from app.modules.data_pipeline import repository
from app.modules.data_pipeline.schemas import PIPELINE_RUN_TYPE_INCREMENTAL_SYNC

logger = logging.getLogger(__name__)

# Default look-back window when there is no prior successful run.
_DEFAULT_LOOKBACK_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def get_checkpoint_window(
    db: firestore.AsyncClient,
    *,
    store_id: str,
) -> tuple[datetime, datetime]:
    """
    Return (checkpoint_start, checkpoint_end) for the next sync window.

    checkpoint_start  = checkpoint_end of the last succeeded run (or epoch).
    checkpoint_end    = utcnow() at the moment this function is called.

    The caller stores these values in the pipeline_runs document and passes
    them to the BigQuery loader. The window is closed (i.e., checkpoint_end
    is captured once and not recalculated mid-run) so that the raw load
    and the mart refresh cover the same batch of records.
    """
    checkpoint_end = _utcnow()

    last_run = await repository.get_last_successful_run(
        db,
        store_id=store_id,
        run_type=PIPELINE_RUN_TYPE_INCREMENTAL_SYNC,
    )

    if last_run and last_run.get("checkpoint_end"):
        raw_start = last_run["checkpoint_end"]
        # Firestore may return a DatetimWithNanoseconds; normalise to UTC datetime
        if hasattr(raw_start, "seconds"):
            checkpoint_start = datetime.fromtimestamp(raw_start.seconds, tz=timezone.utc)
        elif isinstance(raw_start, datetime):
            checkpoint_start = raw_start.replace(tzinfo=timezone.utc) if raw_start.tzinfo is None else raw_start
        else:
            checkpoint_start = _utcnow() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)
    else:
        checkpoint_start = _utcnow() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)
        logger.info(
            "No prior successful checkpoint found. Starting from default look-back.",
            extra={"store_id": store_id, "lookback_days": _DEFAULT_LOOKBACK_DAYS},
        )

    logger.info(
        "Checkpoint window resolved",
        extra={
            "store_id": store_id,
            "checkpoint_start": checkpoint_start.isoformat(),
            "checkpoint_end": checkpoint_end.isoformat(),
        },
    )
    return checkpoint_start, checkpoint_end
