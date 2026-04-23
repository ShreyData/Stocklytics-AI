"""
Data Pipeline Module – Pydantic schemas.

Covers the three API endpoints from api_contracts.md §9:
    POST  /api/v1/pipeline/runs/sync
    GET   /api/v1/pipeline/runs/{pipeline_run_id}
    GET   /api/v1/pipeline/failures

All field names follow the shared naming conventions (snake_case).
Status constants use UPPER_SNAKE_CASE per rules/naming_and_conventions.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Status constants – match database_design.md exactly
# ---------------------------------------------------------------------------

PIPELINE_RUN_STATUS_QUEUED = "QUEUED"
PIPELINE_RUN_STATUS_RUNNING = "RUNNING"
PIPELINE_RUN_STATUS_SUCCEEDED = "SUCCEEDED"
PIPELINE_RUN_STATUS_FAILED = "FAILED"

PIPELINE_RUN_TYPE_INCREMENTAL_SYNC = "INCREMENTAL_SYNC"
PIPELINE_RUN_TYPE_MART_REFRESH = "MART_REFRESH"
PIPELINE_RUN_TYPE_REPAIR = "REPAIR"

DEAD_LETTER_STATUS_OPEN = "OPEN"
DEAD_LETTER_STATUS_REPROCESSING = "REPROCESSING"
DEAD_LETTER_STATUS_RECOVERED = "RECOVERED"

TRIGGER_MODE_SCHEDULED = "scheduled"
TRIGGER_MODE_MANUAL = "manual"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class PipelineSyncRequest(BaseModel):
    """
    Payload for POST /api/v1/pipeline/runs/sync.
    Contract from api_contracts.md §9.
    """

    store_id: str = Field(..., min_length=1, max_length=100)
    trigger_mode: str = Field(
        default=TRIGGER_MODE_MANUAL,
        description="'manual' or 'scheduled'",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PipelineRunResponse(BaseModel):
    """
    Representation of a pipeline_runs document in API responses.
    Matches the GET /api/v1/pipeline/runs/{pipeline_run_id} contract.
    """

    pipeline_run_id: str
    status: str
    attempt_count: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    failure_stage: Optional[str] = None
    error_message: Optional[str] = None


class PipelineFailureResponse(BaseModel):
    """
    Representation of a pipeline_failures document.
    Matches the GET /api/v1/pipeline/failures contract.
    """

    failure_id: str
    pipeline_run_id: str
    source_module: str
    retry_count: int
    dead_letter_status: str
    created_at: datetime
