"""
Alerts Module – FastAPI route handlers.

Base path (registered in main.py): /api/v1/alerts

Endpoints:
    GET  /                          – list alerts (filterable by status, type, severity)
    GET  /summary                   – alert count cards for the dashboard
    POST /{alert_id}/acknowledge    – move ACTIVE alert to ACKNOWLEDGED
    POST /{alert_id}/resolve        – move ACTIVE or ACKNOWLEDGED alert to RESOLVED

Route handlers are intentionally thin: they validate input via Pydantic,
delegate to the service layer, and return structured responses.

Alert lifecycle states (per alerts_logic.md):
    ACTIVE -> ACKNOWLEDGED -> RESOLVED
    ACTIVE -> RESOLVED  (direct skip is allowed)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.common.auth import AuthenticatedUser, require_auth
from app.common.responses import success_response
from app.modules.alerts import service
from app.modules.alerts.schemas import (
    VALID_ALERT_STATUSES,
    VALID_ALERT_TYPES,
    VALID_ALERT_SEVERITIES,
    AcknowledgeRequest,
    ResolveRequest,
)
from app.common.exceptions import ValidationError as AppValidationError

logger = logging.getLogger(__name__)

router = APIRouter()


class InvalidAlertQueryError(AppValidationError):
    """Raised when alerts query parameters fail validation."""

    error_code = "INVALID_QUERY"


# ---------------------------------------------------------------------------
# GET /api/v1/alerts
# ---------------------------------------------------------------------------

@router.get("/", status_code=200)
async def list_alerts(
    store_id: Optional[str] = Query(
        default=None,
        description="Store scope. Must match authenticated store_id when provided.",
    ),
    status: Optional[str] = Query(
        default=None,
        description="Filter by alert lifecycle status: ACTIVE, ACKNOWLEDGED, or RESOLVED.",
    ),
    alert_type: Optional[str] = Query(
        default=None,
        description="Filter by alert type: LOW_STOCK, EXPIRY_SOON, NOT_SELLING, HIGH_DEMAND.",
    ),
    severity: Optional[str] = Query(
        default=None,
        description="Filter by severity: LOW, MEDIUM, HIGH, CRITICAL.",
    ),
    user: AuthenticatedUser = Depends(require_auth),
):
    """
    List alerts for the caller's store.

    Supports optional query filters:
        - status=ACTIVE|ACKNOWLEDGED|RESOLVED
        - alert_type=LOW_STOCK|EXPIRY_SOON|NOT_SELLING|HIGH_DEMAND
        - severity=LOW|MEDIUM|HIGH|CRITICAL
    """
    # Validate store scope if explicitly provided
    if store_id is not None and store_id != user.store_id:
        raise InvalidAlertQueryError(
            "store_id query param must match authenticated store scope.",
            details={"request_store_id": store_id, "auth_store_id": user.store_id},
        )

    # Validate enum query params
    if status is not None and status not in VALID_ALERT_STATUSES:
        raise InvalidAlertQueryError(
            f"Invalid status filter. Must be one of: {sorted(VALID_ALERT_STATUSES)}",
            details={"status": status},
        )
    if alert_type is not None and alert_type not in VALID_ALERT_TYPES:
        raise InvalidAlertQueryError(
            f"Invalid alert_type filter. Must be one of: {sorted(VALID_ALERT_TYPES)}",
            details={"alert_type": alert_type},
        )
    if severity is not None and severity not in VALID_ALERT_SEVERITIES:
        raise InvalidAlertQueryError(
            f"Invalid severity filter. Must be one of: {sorted(VALID_ALERT_SEVERITIES)}",
            details={"severity": severity},
        )

    items = await service.list_alerts(
        store_id=user.store_id,
        status=status,
        alert_type=alert_type,
        severity=severity,
    )
    return success_response({"items": items})


@router.get("", status_code=200, include_in_schema=False)
async def list_alerts_without_trailing_slash(
    store_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    alert_type: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    user: AuthenticatedUser = Depends(require_auth),
):
    return await list_alerts(
        store_id=store_id,
        status=status,
        alert_type=alert_type,
        severity=severity,
        user=user,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/alerts/summary
# ---------------------------------------------------------------------------

@router.get("/summary", status_code=200)
async def get_alerts_summary(
    store_id: Optional[str] = Query(
        default=None,
        description="Store scope. Must match authenticated store_id when provided.",
    ),
    user: AuthenticatedUser = Depends(require_auth),
):
    """
    Return alert count breakdown for dashboard cards:
        active, acknowledged, resolved_today.
    """
    if store_id is not None and store_id != user.store_id:
        raise InvalidAlertQueryError(
            "store_id query param must match authenticated store scope.",
            details={"request_store_id": store_id, "auth_store_id": user.store_id},
        )

    summary = await service.get_alerts_summary(store_id=user.store_id)
    return success_response({"summary": summary})


# ---------------------------------------------------------------------------
# POST /api/v1/alerts/{alert_id}/acknowledge
# ---------------------------------------------------------------------------

@router.post("/{alert_id}/acknowledge", status_code=200)
async def acknowledge_alert(
    alert_id: str,
    payload: AcknowledgeRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """
    Move an ACTIVE alert to ACKNOWLEDGED.

    Validates that the alert belongs to the caller's store and that the
    current status allows the ACKNOWLEDGED transition.
    """
    # store_id in body must match authenticated scope
    if payload.store_id != user.store_id:
        raise AppValidationError(
            "store_id in request must match authenticated store scope.",
            details={
                "request_store_id": payload.store_id,
                "auth_store_id": user.store_id,
            },
        )

    alert = await service.acknowledge_alert(
        alert_id=alert_id,
        store_id=user.store_id,
        user_id=user.user_id,
        note=payload.note,
    )
    return success_response({"alert": alert})


# ---------------------------------------------------------------------------
# POST /api/v1/alerts/{alert_id}/resolve
# ---------------------------------------------------------------------------

@router.post("/{alert_id}/resolve", status_code=200)
async def resolve_alert(
    alert_id: str,
    payload: ResolveRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """
    Move an ACTIVE or ACKNOWLEDGED alert to RESOLVED.

    Validates that the alert belongs to the caller's store and that the
    current status allows the RESOLVED transition.
    """
    if payload.store_id != user.store_id:
        raise AppValidationError(
            "store_id in request must match authenticated store scope.",
            details={
                "request_store_id": payload.store_id,
                "auth_store_id": user.store_id,
            },
        )

    alert = await service.resolve_alert(
        alert_id=alert_id,
        store_id=user.store_id,
        user_id=user.user_id,
        resolution_note=payload.resolution_note,
    )
    return success_response({"alert": alert})
