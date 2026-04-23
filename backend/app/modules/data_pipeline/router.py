"""
Data Pipeline Module – FastAPI router.

Exposes the endpoints defined in api_contracts.md §9:
    POST  /api/v1/pipeline/runs/sync          (Admin only)
    GET   /api/v1/pipeline/runs/{pipeline_run_id} (Admin/Manager)
    GET   /api/v1/pipeline/failures           (Admin only)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path

from app.common.auth import Role, require_role, get_current_store_id
from app.common.responses import success_response
from app.modules.data_pipeline import service
from app.modules.data_pipeline.schemas import PipelineSyncRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pipeline",
    tags=["data_pipeline"],
    responses={404: {"description": "Not found"}},
)


@router.post(
    "/runs/sync",
    status_code=202,
    summary="Trigger Manual Pipeline Sync",
)
async def trigger_pipeline_sync(
    request: PipelineSyncRequest,
    _admin=Depends(require_role([Role.ADMIN])),
    store_id: str = Depends(get_current_store_id),
):
    """
    Trigger an incremental sync from Firestore to BigQuery.
    
    Validates that no pipeline run is currently active for this store.
    Returns 202 Accepted and a pipeline_run_id.
    """
    # Enforce request store_id matches authenticated token's store
    if request.store_id != store_id:
        from app.common.exceptions import ForbiddenError # noqa: PLC0415
        raise ForbiddenError(
            "Request store_id does not match token scope.",
            details={"error_code": "FORBIDDEN"},
        )
        
    result = await service.trigger_sync(store_id=store_id)
    return success_response(result, status_code=202)


@router.get(
    "/runs/{pipeline_run_id}",
    status_code=200,
    summary="Get Pipeline Run Status",
)
async def get_pipeline_run_status(
    pipeline_run_id: str = Path(..., description="ID of the pipeline run to fetch"),
    _auth=Depends(require_role([Role.ADMIN, Role.MANAGER])),
    store_id: str = Depends(get_current_store_id),
):
    """
    Fetch the status and details of a specific pipeline run.
    """
    result = await service.get_pipeline_run(
        pipeline_run_id=pipeline_run_id,
        store_id=store_id,
    )
    return success_response(result, status_code=200)


@router.get(
    "/failures",
    status_code=200,
    summary="List Pipeline Failures",
)
async def list_pipeline_failures(
    _admin=Depends(require_role([Role.ADMIN])),
    store_id: str = Depends(get_current_store_id),
):
    """
    List OPEN pipeline failures (dead-letter queue) for the store.
    """
    result = await service.list_pipeline_failures(store_id=store_id)
    return success_response(result, status_code=200)
