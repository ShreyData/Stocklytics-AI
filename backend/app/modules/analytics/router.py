"""
Analytics Module router.

Owned by: Analytics Module developer.
Base path: /api/v1/analytics
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.common.auth import AuthenticatedUser, require_auth
from app.common.responses import success_response
from app.modules.analytics.service import AnalyticsService
from app.modules.analytics.service import InvalidAnalyticsQueryError

router = APIRouter()
analytics_service = AnalyticsService()

@router.get("/dashboard", status_code=200)
async def get_dashboard_summary(user: AuthenticatedUser = Depends(require_auth)):
    response_data = await analytics_service.get_dashboard_summary(user.store_id)
    return success_response(response_data, status_code=200)

@router.get("/sales-trends", status_code=200)
async def get_sales_trends(
    store_id: Optional[str] = Query(default=None),
    range: str = Query(default="30d"),
    granularity: str = Query(default="daily"),
    user: AuthenticatedUser = Depends(require_auth),
):
    if store_id is not None and store_id != user.store_id:
        raise InvalidAnalyticsQueryError(
            "store_id query param must match authenticated store scope.",
            details={"request_store_id": store_id, "auth_store_id": user.store_id},
        )
    response_data = await analytics_service.get_sales_trends(
        store_id=user.store_id,
        range_value=range,
        granularity=granularity,
    )
    return success_response(response_data, status_code=200)

@router.get("/product-performance", status_code=200)
async def get_product_performance(user: AuthenticatedUser = Depends(require_auth)):
    response_data = await analytics_service.get_product_performance(user.store_id)
    return success_response(response_data, status_code=200)

@router.get("/customer-insights", status_code=200)
async def get_customer_insights(user: AuthenticatedUser = Depends(require_auth)):
    response_data = await analytics_service.get_customer_insights(user.store_id)
    return success_response(response_data, status_code=200)
