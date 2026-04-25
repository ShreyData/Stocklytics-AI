"""
Platform endpoints for RetailMind AI.

Exposes:
    GET /api/v1/health   – liveness check (no auth required)
    GET /api/v1/ready    – readiness check with dependency probes (no auth required)
    GET /api/v1/me       – authenticated user profile
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.common.auth import AuthenticatedUser, require_auth
from app.common.config import get_settings
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

_PROBE_TIMEOUT_SECONDS = 2.5


async def _run_with_timeout(coro) -> str:
    """
    Run a probe coroutine with a timeout and standard error normalization.

    Returns:
        - "ok"
        - "not_configured"
        - "error"
    """
    try:
        return await asyncio.wait_for(coro, timeout=_PROBE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return "error"
    except Exception:  # noqa: BLE001
        return "error"


async def _probe_firestore() -> str:
    """
    Firestore connectivity check.

    Local/dev behavior:
        - if FIRESTORE_PROJECT_ID is missing -> not_configured
    Runtime behavior:
        - attempts a minimal list_collections call
    """
    settings = get_settings()
    if not settings.firestore_project_id:
        return "not_configured" if settings.is_local else "error"

    def _ping_firestore() -> str:
        from google.cloud import firestore

        client = firestore.Client(project=settings.firestore_project_id or None)
        # Minimal API call to verify credentials and service reachability.
        list(client.collections(page_size=1))
        return "ok"

    try:
        return await asyncio.to_thread(_ping_firestore)
    except Exception:  # noqa: BLE001
        logger.exception("Firestore readiness probe failed")
        return "error"


async def _probe_bigquery() -> str:
    """
    BigQuery connectivity check.

    Local/dev behavior:
        - if BIGQUERY_PROJECT_ID is missing -> not_configured
    Runtime behavior:
        - executes SELECT 1
    """
    settings = get_settings()
    if not settings.bigquery_project_id:
        return "not_configured" if settings.is_local else "error"

    def _ping_bigquery() -> str:
        from google.cloud import bigquery

        client = bigquery.Client(project=settings.bigquery_project_id or None)
        query_job = client.query("SELECT 1 AS ready_check")
        query_job.result(timeout=2)
        return "ok"

    try:
        return await asyncio.to_thread(_ping_bigquery)
    except Exception:  # noqa: BLE001
        logger.exception("BigQuery readiness probe failed")
        return "error"


async def _probe_gemini() -> str:
    """
    Gemini connectivity check.

    Local/dev behavior:
        - if GEMINI_API_KEY is missing -> not_configured
    Runtime behavior:
        - lists one available model
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return "not_configured" if settings.is_local else "error"

    def _ping_gemini() -> str:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        # Trigger a lightweight API call.
        next(iter(genai.list_models()), None)
        return "ok"

    try:
        return await asyncio.to_thread(_ping_gemini)
    except Exception:  # noqa: BLE001
        logger.exception("Gemini readiness probe failed")
        return "error"


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
    firestore_status, bigquery_status, gemini_status = await asyncio.gather(
        _run_with_timeout(_probe_firestore()),
        _run_with_timeout(_probe_bigquery()),
        _run_with_timeout(_probe_gemini()),
    )

    dependencies = {
        "firestore": firestore_status,
        "bigquery": bigquery_status,
        "gemini": gemini_status,
    }
    has_error = any(dep_status == "error" for dep_status in dependencies.values())

    if has_error:
        logger.warning("Readiness check failed", extra={"dependencies": dependencies})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "dependencies": dependencies,
            },
        )

    logger.info("Readiness check completed", extra={"dependencies": dependencies})
    return {
        "status": "ready",
        "dependencies": dependencies,
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
