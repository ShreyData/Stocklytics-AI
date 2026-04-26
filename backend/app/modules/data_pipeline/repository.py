"""
Data Pipeline Module – Firestore repository.

Handles all Firestore reads and writes for:
    - pipeline_runs  (execution log)
    - pipeline_failures  (dead-letter store)
    - analytics_metadata  (freshness stamp, written only on success)

Collection and field names match database_design.md exactly.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore  # type: ignore

from app.modules.data_pipeline.schemas import (
    PIPELINE_RUN_STATUS_QUEUED,
    PIPELINE_RUN_STATUS_RUNNING,
    PIPELINE_RUN_STATUS_SUCCEEDED,
    PIPELINE_RUN_STATUS_FAILED,
    DEAD_LETTER_STATUS_OPEN,
)

logger = logging.getLogger(__name__)

# Firestore collection names – match database_design.md §3 exactly
_COLLECTION_PIPELINE_RUNS = "pipeline_runs"
_COLLECTION_PIPELINE_FAILURES = "pipeline_failures"
_COLLECTION_ANALYTICS_METADATA = "analytics_metadata"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# pipeline_runs helpers
# ---------------------------------------------------------------------------

async def create_pipeline_run(
    db: firestore.AsyncClient,
    *,
    store_id: str,
    run_type: str,
    checkpoint_start: Optional[datetime],
    checkpoint_end: Optional[datetime],
) -> str:
    """
    Insert a new pipeline_runs document with status QUEUED.
    Returns the generated pipeline_run_id.
    """
    pipeline_run_id = f"pipe_run_{uuid.uuid4().hex[:12]}"
    doc_ref = db.collection(_COLLECTION_PIPELINE_RUNS).document(pipeline_run_id)

    data: dict = {
        "pipeline_run_id": pipeline_run_id,
        "store_id": store_id,
        "run_type": run_type,
        "status": PIPELINE_RUN_STATUS_QUEUED,
        "attempt_count": 0,
        "checkpoint_start": checkpoint_start,
        "checkpoint_end": checkpoint_end,
        "records_read": 0,
        "records_written": 0,
        "failure_stage": None,
        "error_message": None,
        "started_at": _utcnow(),
        "finished_at": None,
    }

    await doc_ref.set(data)
    logger.info(
        "Pipeline run created",
        extra={"pipeline_run_id": pipeline_run_id, "store_id": store_id, "run_type": run_type},
    )
    return pipeline_run_id


async def update_pipeline_run_running(
    db: firestore.AsyncClient,
    *,
    pipeline_run_id: str,
    attempt_count: int,
) -> None:
    """Mark the run as RUNNING and update attempt count."""
    doc_ref = db.collection(_COLLECTION_PIPELINE_RUNS).document(pipeline_run_id)
    await doc_ref.update({
        "status": PIPELINE_RUN_STATUS_RUNNING,
        "attempt_count": attempt_count,
    })


async def mark_pipeline_run_succeeded(
    db: firestore.AsyncClient,
    *,
    pipeline_run_id: str,
    records_read: int,
    records_written: int,
    checkpoint_end: datetime,
) -> None:
    """Mark the run as SUCCEEDED and stamp completion time."""
    doc_ref = db.collection(_COLLECTION_PIPELINE_RUNS).document(pipeline_run_id)
    await doc_ref.update({
        "status": PIPELINE_RUN_STATUS_SUCCEEDED,
        "records_read": records_read,
        "records_written": records_written,
        "checkpoint_end": checkpoint_end,
        "finished_at": _utcnow(),
        "failure_stage": None,
        "error_message": None,
    })
    logger.info("Pipeline run succeeded", extra={"pipeline_run_id": pipeline_run_id})


async def mark_pipeline_run_failed(
    db: firestore.AsyncClient,
    *,
    pipeline_run_id: str,
    attempt_count: int,
    failure_stage: str,
    error_message: str,
) -> None:
    """
    Mark the run as FAILED.
    Checkpoint is NOT advanced – caller must not update checkpoint_end.
    """
    doc_ref = db.collection(_COLLECTION_PIPELINE_RUNS).document(pipeline_run_id)
    await doc_ref.update({
        "status": PIPELINE_RUN_STATUS_FAILED,
        "attempt_count": attempt_count,
        "failure_stage": failure_stage,
        "error_message": error_message[:1000],  # trim very long stack traces
        "finished_at": _utcnow(),
    })
    logger.error(
        "Pipeline run failed",
        extra={
            "pipeline_run_id": pipeline_run_id,
            "failure_stage": failure_stage,
            "error_message": error_message,
        },
    )


async def get_pipeline_run(
    db: firestore.AsyncClient,
    *,
    pipeline_run_id: str,
) -> Optional[dict]:
    """Fetch a single pipeline_runs document. Returns None if not found."""
    doc = await db.collection(_COLLECTION_PIPELINE_RUNS).document(pipeline_run_id).get()
    if not doc.exists:
        return None
    return doc.to_dict()


async def get_active_run_for_store(
    db: firestore.AsyncClient,
    *,
    store_id: str,
) -> Optional[dict]:
    """
    Return any QUEUED or RUNNING pipeline run for this store.
    Used to enforce PIPELINE_ALREADY_RUNNING guard.
    """
    query = (
        db.collection(_COLLECTION_PIPELINE_RUNS)
        .where("store_id", "==", store_id)
        .where("status", "in", [PIPELINE_RUN_STATUS_QUEUED, PIPELINE_RUN_STATUS_RUNNING])
        .limit(1)
    )
    async for doc in query.stream():
        return doc.to_dict()
    return None


async def get_last_successful_run(
    db: firestore.AsyncClient,
    *,
    store_id: str,
    run_type: Optional[str] = None,
) -> Optional[dict]:
    """
    Return the most recent SUCCEEDED pipeline_run for this store.
    Used by checkpoint_manager to determine the next incremental window.
    """
    query = (
        db.collection(_COLLECTION_PIPELINE_RUNS)
        .where("store_id", "==", store_id)
        .where("status", "==", PIPELINE_RUN_STATUS_SUCCEEDED)
    )
    if run_type is not None:
        query = query.where("run_type", "==", run_type)
    query = query.order_by("finished_at", direction=firestore.Query.DESCENDING).limit(1)
    async for doc in query.stream():
        return doc.to_dict()
    return None


# ---------------------------------------------------------------------------
# pipeline_failures helpers
# ---------------------------------------------------------------------------

async def write_pipeline_failure(
    db: firestore.AsyncClient,
    *,
    pipeline_run_id: str,
    store_id: str,
    source_module: str,
    batch_ref: str,
    retry_count: int,
    failure_stage: str,
    error_message: str,
) -> str:
    """
    Write an exhausted-retry failure into pipeline_failures.
    Returns the failure_id.
    """
    failure_id = f"pf_{uuid.uuid4().hex[:12]}"
    doc_ref = db.collection(_COLLECTION_PIPELINE_FAILURES).document(failure_id)

    await doc_ref.set({
        "failure_id": failure_id,
        "pipeline_run_id": pipeline_run_id,
        "store_id": store_id,
        "source_module": source_module,
        "batch_ref": batch_ref,
        "retry_count": retry_count,
        "failure_stage": failure_stage,
        "dead_letter_status": DEAD_LETTER_STATUS_OPEN,
        "error_message": error_message[:1000],
        "created_at": _utcnow(),
        "recovered_at": None,
    })

    logger.warning(
        "Pipeline failure recorded",
        extra={
            "failure_id": failure_id,
            "pipeline_run_id": pipeline_run_id,
            "source_module": source_module,
            "failure_stage": failure_stage,
        },
    )
    return failure_id


async def list_pipeline_failures(
    db: firestore.AsyncClient,
    *,
    store_id: str,
    limit: int = 50,
) -> list[dict]:
    """
    List OPEN pipeline_failures for a store, newest first.
    Used by GET /api/v1/pipeline/failures.
    """
    query = (
        db.collection(_COLLECTION_PIPELINE_FAILURES)
        .where("store_id", "==", store_id)
        .where("dead_letter_status", "==", DEAD_LETTER_STATUS_OPEN)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    results = []
    async for doc in query.stream():
        results.append(doc.to_dict())
    return results


async def mark_failure_reprocessing(
    db: firestore.AsyncClient,
    *,
    failure_id: str,
) -> None:
    """Mark a failure as REPROCESSING when repair job picks it up."""
    await db.collection(_COLLECTION_PIPELINE_FAILURES).document(failure_id).update(
        {"dead_letter_status": "REPROCESSING"}
    )


async def mark_failure_open(
    db: firestore.AsyncClient,
    *,
    failure_id: str,
) -> None:
    """Move a failure back to OPEN so it can be retried by a later repair run."""
    await db.collection(_COLLECTION_PIPELINE_FAILURES).document(failure_id).update(
        {"dead_letter_status": DEAD_LETTER_STATUS_OPEN}
    )


async def mark_failure_recovered(
    db: firestore.AsyncClient,
    *,
    failure_id: str,
) -> None:
    """Mark a failure as RECOVERED after successful repair."""
    await db.collection(_COLLECTION_PIPELINE_FAILURES).document(failure_id).update({
        "dead_letter_status": "RECOVERED",
        "recovered_at": _utcnow(),
    })


# ---------------------------------------------------------------------------
# analytics_metadata helpers
# ---------------------------------------------------------------------------

async def update_analytics_metadata(
    db: firestore.AsyncClient,
    *,
    store_id: str,
    pipeline_run_id: str,
    source_window_start: datetime,
    source_window_end: datetime,
) -> None:
    """
    Write analytics_metadata freshness stamp after a successful mart refresh.

    Rule (database_design.md §6, shared_business_rules.md §10):
        analytics_last_updated_at MUST NOT be updated on a failed run.
        Caller is responsible for only calling this on confirmed success.

    Freshness status is always 'fresh' at the moment of a successful refresh.
    """
    metadata_id = f"{store_id}_dashboard"
    doc_ref = db.collection(_COLLECTION_ANALYTICS_METADATA).document(metadata_id)

    now = _utcnow()
    await doc_ref.set({
        "metadata_id": metadata_id,
        "store_id": store_id,
        "analytics_last_updated_at": now,
        "freshness_status": "fresh",
        "last_pipeline_run_id": pipeline_run_id,
        "source_window_start": source_window_start,
        "source_window_end": source_window_end,
        "updated_at": now,
    }, merge=True)

    logger.info(
        "Analytics metadata updated",
        extra={
            "store_id": store_id,
            "pipeline_run_id": pipeline_run_id,
            "analytics_last_updated_at": now.isoformat(),
        },
    )
