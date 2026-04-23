"""
Data Pipeline Module – Service Layer.

Business logic called by the router. Keeps route handlers thin.

Responsibilities:
    - Validate business preconditions (e.g., PIPELINE_ALREADY_RUNNING guard)
    - Acquire Firestore and BigQuery clients
    - Delegate to sync_runner, transform_runner, and repository
    - Return plain dicts that the router wraps via success_response()

Rule: this service does NOT handle HTTP concerns (status codes, JSONResponse).
The router is responsible for that.
"""

from __future__ import annotations

import logging

from google.cloud import bigquery as bq_client_module  # type: ignore
from google.cloud import firestore as fs_client_module  # type: ignore

from app.common.config import get_settings
from app.common.exceptions import ConflictError, NotFoundError
from app.modules.data_pipeline import repository, sync_runner
from app.modules.data_pipeline.schemas import (
    PIPELINE_RUN_STATUS_QUEUED,
)

logger = logging.getLogger(__name__)

_settings = get_settings()


# ---------------------------------------------------------------------------
# Client factories (module-level singletons, created lazily)
# ---------------------------------------------------------------------------

_firestore_client: fs_client_module.AsyncClient | None = None
_bigquery_client: bq_client_module.Client | None = None


def _get_firestore() -> fs_client_module.AsyncClient:
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = fs_client_module.AsyncClient(
            project=_settings.firestore_project_id or None
        )
    return _firestore_client


def _get_bigquery() -> bq_client_module.Client:
    global _bigquery_client
    if _bigquery_client is None:
        _bigquery_client = bq_client_module.Client(
            project=_settings.bigquery_project_id or None
        )
    return _bigquery_client


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

async def trigger_sync(*, store_id: str) -> dict:
    """
    Trigger an incremental sync run for one store.

    Returns the API response dict for POST /api/v1/pipeline/runs/sync (202).
    Raises ConflictError if a run is already active.
    """
    db = _get_firestore()
    bq = _get_bigquery()

    # Guard: PIPELINE_ALREADY_RUNNING (api_contracts.md §9)
    active = await repository.get_active_run_for_store(db, store_id=store_id)
    if active:
        e = ConflictError(
            "A pipeline run is already active for this store.",
            details={"active_pipeline_run_id": active.get("pipeline_run_id")},
        )
        e.error_code = "PIPELINE_ALREADY_RUNNING"
        raise e

    import asyncio  # noqa: PLC0415
    
    # Create the pipeline run record immediately so we have an ID to return
    # and the active guard works immediately.
    # We must resolve the window synchronously before firing the background task.
    from app.modules.data_pipeline import checkpoint_manager
    checkpoint_start, checkpoint_end = await checkpoint_manager.get_checkpoint_window(db, store_id=store_id)
    
    pipeline_run_id = await repository.create_pipeline_run(
        db,
        store_id=store_id,
        run_type="INCREMENTAL_SYNC",
        checkpoint_start=checkpoint_start,
        checkpoint_end=checkpoint_end,
    )
    
    # Fire and forget the background task.
    task = asyncio.create_task(
        sync_runner.run_incremental_sync(
            db,
            bq,
            store_id=store_id,
            precreated_run_id=pipeline_run_id,
            checkpoint_override=(checkpoint_start, checkpoint_end),
        )
    )

    def _log_task_error(done_task: asyncio.Task) -> None:
        try:
            done_task.result()
        except Exception:  # noqa: BLE001
            logger.exception(
                "Background sync task failed",
                extra={"pipeline_run_id": pipeline_run_id, "store_id": store_id},
            )

    task.add_done_callback(_log_task_error)

    logger.info(
        "Sync triggered via API",
        extra={"pipeline_run_id": pipeline_run_id, "store_id": store_id},
    )

    return {
        "pipeline_run_id": pipeline_run_id,
        "status": PIPELINE_RUN_STATUS_QUEUED,
    }


async def get_pipeline_run(*, pipeline_run_id: str, store_id: str) -> dict:
    """
    Fetch a pipeline_runs document.

    Raises NotFoundError (404 PIPELINE_RUN_NOT_FOUND) if not found or
    if the run belongs to a different store.
    """
    db = _get_firestore()

    run = await repository.get_pipeline_run(db, pipeline_run_id=pipeline_run_id)

    if run is None:
        e = NotFoundError(f"Pipeline run '{pipeline_run_id}' was not found.")
        e.error_code = "PIPELINE_RUN_NOT_FOUND"
        raise e

    # Scope guard: ensure the run belongs to the requesting store
    if run.get("store_id") != store_id:
        e = NotFoundError(f"Pipeline run '{pipeline_run_id}' was not found.")
        e.error_code = "PIPELINE_RUN_NOT_FOUND"
        raise e

    return {
        "pipeline_run": {
            "pipeline_run_id": run["pipeline_run_id"],
            "status": run["status"],
            "attempt_count": run.get("attempt_count", 0),
            "started_at": _serialise_ts(run.get("started_at")),
            "finished_at": _serialise_ts(run.get("finished_at")),
            "failure_stage": run.get("failure_stage"),
            "error_message": run.get("error_message"),
        }
    }


async def list_pipeline_failures(*, store_id: str) -> dict:
    """
    List OPEN pipeline_failures for the requesting store.

    Returns the API response dict for GET /api/v1/pipeline/failures (200).
    """
    db = _get_firestore()
    failures = await repository.list_pipeline_failures(db, store_id=store_id)

    items = [
        {
            "failure_id": f.get("failure_id"),
            "pipeline_run_id": f.get("pipeline_run_id"),
            "source_module": f.get("source_module"),
            "retry_count": f.get("retry_count", 0),
            "dead_letter_status": f.get("dead_letter_status"),
            "created_at": _serialise_ts(f.get("created_at")),
        }
        for f in failures
    ]

    return {"items": items}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialise_ts(value) -> str | None:
    """Convert a Firestore timestamp or datetime to ISO-8601 string."""
    if value is None:
        return None
    from datetime import datetime, timezone  # noqa: PLC0415
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if hasattr(value, "seconds"):
        return datetime.fromtimestamp(value.seconds, tz=timezone.utc).isoformat()
    return str(value)
