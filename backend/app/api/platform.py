"""
Platform endpoints for RetailMind AI.

Exposes:
    GET /api/v1/health   – liveness check (no auth required)
    GET /api/v1/ready    – readiness check with dependency probes (no auth required)
    GET /api/v1/me       – authenticated user profile
"""

import logging

from fastapi import APIRouter, Depends

from app.common.auth import AuthenticatedUser, require_auth
from app.common.responses import success_response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Platform"])


# ---------------------------------------------------------------------------
# GET /api/v1/health
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    summary="Liveness check",
    description="Returns 200 when the API process is running.",
    response_description="Service is alive.",
)
async def health_check():
    """
    Liveness probe.
    Cloud Run and load balancers use this to confirm the process is alive.
    No authentication required.
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /api/v1/ready
# ---------------------------------------------------------------------------

async def _probe_firestore() -> str:
    """
    Lightweight Firestore connectivity check.
    In the API-foundation phase this is a stub that returns 'ok'.
    Replace with an actual Firestore ping when the Firestore client is wired in.
    """
    # TODO: replace with real Firestore ping once client is initialised
    return "ok"


async def _probe_bigquery() -> str:
    """
    Lightweight BigQuery connectivity check (stub for API-foundation phase).
    Replace with a real query once BigQuery client is wired in.
    """
    # TODO: replace with real BigQuery ping once client is initialised
    return "ok"


async def _probe_gemini() -> str:
    """
    Lightweight Gemini API connectivity check (stub for API-foundation phase).
    Replace with a real models.list call once Gemini client is wired in.
    """
    # TODO: replace with real Gemini ping once client is initialised
    return "ok"


@router.get(
    "/ready",
    summary="Readiness check",
    description=(
        "Probes Firestore, BigQuery, and Gemini dependencies. "
        "Returns 200 when all critical dependencies are reachable."
    ),
    response_description="All dependencies are ready.",
)
async def readiness_check():
    """
    Readiness probe.
    Returns the status of each downstream dependency so orchestrators and
    health dashboards can surface partial outages quickly.
    No authentication required.
    """
    firestore_status = await _probe_firestore()
    bigquery_status = await _probe_bigquery()
    gemini_status = await _probe_gemini()

    logger.info("Readiness check completed")
    return {
        "status": "ready",
        "dependencies": {
            "firestore": firestore_status,
            "bigquery": bigquery_status,
            "gemini": gemini_status,
        },
    }


# ---------------------------------------------------------------------------
# GET /api/v1/me
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    summary="Authenticated user profile",
    description="Returns the currently authenticated user's profile from their token claims.",
    response_description="User profile.",
)
async def get_me(
    user: AuthenticatedUser = Depends(require_auth),
):
    """
    Returns user_id, role, and store_id extracted from the verified Firebase token.
    The request_id is injected automatically by the success_response helper.
    """
    logger.info(
        "User profile requested",
        extra={"user_id": user.user_id, "store_id": user.store_id},
    )
    return success_response(
        {
            "user": {
                "user_id": user.user_id,
                "role": user.role,
                "store_id": user.store_id,
                "email": user.email,
            }
        }
    )
