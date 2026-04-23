"""
Analytics Module router.

Owned by: Analytics Module developer.
Base path: /api/v1/analytics
"""

from fastapi import APIRouter, Depends

from app.common.auth import AuthenticatedUser, require_auth
from app.common.responses import success_response
from app.modules.analytics.service import AnalyticsService

router = APIRouter()
analytics_service = AnalyticsService()

@router.get("/dashboard", status_code=200)
async def get_dashboard_summary(user: AuthenticatedUser = Depends(require_auth)):
    response_data = await analytics_service.get_dashboard_summary(user.store_id)
    return success_response(response_data, status_code=200)

@router.get("/sales-trends", status_code=200)
async def get_sales_trends(user: AuthenticatedUser = Depends(require_auth)):
    response_data = await analytics_service.get_sales_trends(user.store_id)
    return success_response(response_data, status_code=200)

@router.get("/product-performance", status_code=200)
async def get_product_performance(user: AuthenticatedUser = Depends(require_auth)):
    response_data = await analytics_service.get_product_performance(user.store_id)
    return success_response(response_data, status_code=200)

@router.get("/customer-insights", status_code=200)
async def get_customer_insights(user: AuthenticatedUser = Depends(require_auth)):
    response_data = await analytics_service.get_customer_insights(user.store_id)
    return success_response(response_data, status_code=200)
