"""
RetailMind AI – FastAPI application entry point.

Architecture: modular monolith (see Plan/architecture_overview.md)
Base API path: /api/v1

Startup sequence:
    1. Configure structured JSON logging.
    2. Create the FastAPI app with metadata.
    3. Register global exception handlers.
    4. Register RequestIdMiddleware.
    5. Mount all module routers under /api/v1.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.config import get_settings
from app.common.exceptions import register_exception_handlers
from app.common.logging_config import configure_logging
from app.common.middleware import RequestIdMiddleware

# Platform routes
from app.api.platform import router as platform_router

# Module routes (stub routers – each developer fills these in on their branch)
from app.modules.inventory.router import router as inventory_router
from app.modules.billing.router import router as billing_router
from app.modules.customer.router import router as customer_router
from app.modules.analytics.router import router as analytics_router
from app.modules.alerts.router import router as alerts_router
from app.modules.ai.router import router as ai_router
from app.modules.data_pipeline.router import router as pipeline_router

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="RetailMind AI",
        description=(
            "Modular monolith API for RetailMind AI – "
            "inventory, billing, customers, analytics, alerts, AI, and data pipeline."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ---- Exception handlers (must come before middleware) ----
    register_exception_handlers(application)

    # ---- Middleware ----
    # Order matters: outermost middleware runs first on request, last on response.
    application.add_middleware(RequestIdMiddleware)

    # CORS – locked down by default; adjust origins for production deployments.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_local else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Platform routes (no module prefix) ----
    application.include_router(platform_router, prefix="/api/v1")

    # ---- Module routes ----
    application.include_router(
        inventory_router,
        prefix="/api/v1/inventory",
        tags=["Inventory Module"],
    )
    application.include_router(
        billing_router,
        prefix="/api/v1/billing",
        tags=["Billing Module"],
    )
    application.include_router(
        customer_router,
        prefix="/api/v1/customers",
        tags=["Customer Module"],
    )
    application.include_router(
        analytics_router,
        prefix="/api/v1/analytics",
        tags=["Analytics Module"],
    )
    application.include_router(
        alerts_router,
        prefix="/api/v1/alerts",
        tags=["Alerts Module"],
    )
    application.include_router(
        ai_router,
        prefix="/api/v1/ai",
        tags=["AI Module"],
    )
    application.include_router(
        pipeline_router,
        prefix="/api/v1/pipeline",
        tags=["Data Pipeline Module"],
    )

    logger.info(
        "RetailMind AI started",
        extra={"env": settings.app_env, "port": settings.api_port},
    )

    return application


app = create_app()
