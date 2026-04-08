"""
Data Pipeline Module router stub.

Owned by: Data Pipeline Module developer.
Base path: /api/v1/pipeline

Planned endpoints (implement per data_pipeline_implementation.md):
    POST  /api/v1/pipeline/runs/sync          (admin only)
    GET   /api/v1/pipeline/runs/{pipeline_run_id}
    GET   /api/v1/pipeline/failures

Key rules:
    - Pipeline trigger endpoint is admin-only (use require_admin dependency).
    - Jobs retry up to 3 times on failure.
    - analytics_last_updated_at must NOT advance on a failed pipeline refresh.
"""

from fastapi import APIRouter

router = APIRouter()

# TODO: implement pipeline endpoints per data_pipeline_implementation.md and api_contracts.md
