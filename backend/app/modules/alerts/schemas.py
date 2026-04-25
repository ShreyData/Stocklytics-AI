"""
Alerts Module – Pydantic schemas.

Defines request/response models for all alerts endpoints.
All field names are snake_case per project naming conventions.

Alert lifecycle: ACTIVE -> ACKNOWLEDGED -> RESOLVED
                 ACTIVE -> RESOLVED  (direct)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Status / type / severity constants
# ---------------------------------------------------------------------------

ALERT_STATUS_ACTIVE = "ACTIVE"
ALERT_STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
ALERT_STATUS_RESOLVED = "RESOLVED"

VALID_ALERT_STATUSES = {
    ALERT_STATUS_ACTIVE,
    ALERT_STATUS_ACKNOWLEDGED,
    ALERT_STATUS_RESOLVED,
}

# Transitions that are allowed (from_status -> to_status)
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ALERT_STATUS_ACTIVE: {ALERT_STATUS_ACKNOWLEDGED, ALERT_STATUS_RESOLVED},
    ALERT_STATUS_ACKNOWLEDGED: {ALERT_STATUS_RESOLVED},
    ALERT_STATUS_RESOLVED: set(),
}

ALERT_TYPE_LOW_STOCK = "LOW_STOCK"
ALERT_TYPE_EXPIRY_SOON = "EXPIRY_SOON"
ALERT_TYPE_NOT_SELLING = "NOT_SELLING"
ALERT_TYPE_HIGH_DEMAND = "HIGH_DEMAND"

VALID_ALERT_TYPES = {
    ALERT_TYPE_LOW_STOCK,
    ALERT_TYPE_EXPIRY_SOON,
    ALERT_TYPE_NOT_SELLING,
    ALERT_TYPE_HIGH_DEMAND,
}

ALERT_SEVERITY_LOW = "LOW"
ALERT_SEVERITY_MEDIUM = "MEDIUM"
ALERT_SEVERITY_HIGH = "HIGH"
ALERT_SEVERITY_CRITICAL = "CRITICAL"

VALID_ALERT_SEVERITIES = {
    ALERT_SEVERITY_LOW,
    ALERT_SEVERITY_MEDIUM,
    ALERT_SEVERITY_HIGH,
    ALERT_SEVERITY_CRITICAL,
}


# ---------------------------------------------------------------------------
# Shared alert record schema
# ---------------------------------------------------------------------------

class AlertResponse(BaseModel):
    """Full alert record returned from the API."""

    alert_id: str
    store_id: str
    alert_type: str
    condition_key: str
    source_entity_id: str
    status: str
    severity: str
    title: str
    message: str
    metadata: Optional[dict[str, Any]] = None
    created_at: str                          # ISO-8601 string
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None
    last_evaluated_at: str


# ---------------------------------------------------------------------------
# Lifecycle action request schemas
# ---------------------------------------------------------------------------

class AcknowledgeRequest(BaseModel):
    """Payload for POST /api/v1/alerts/{alert_id}/acknowledge."""

    store_id: str = Field(..., min_length=1, max_length=100)
    note: Optional[str] = Field(default=None, max_length=1000)


class ResolveRequest(BaseModel):
    """Payload for POST /api/v1/alerts/{alert_id}/resolve."""

    store_id: str = Field(..., min_length=1, max_length=100)
    resolution_note: Optional[str] = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Summary schema
# ---------------------------------------------------------------------------

class AlertSummary(BaseModel):
    """Alert count breakdown for dashboard cards."""

    active: int
    acknowledged: int
    resolved_today: int
