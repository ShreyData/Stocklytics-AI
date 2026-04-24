from typing import Any, Dict

from app.common.exceptions import ServiceUnavailableError, ValidationError
from app.modules.analytics.repository import AnalyticsRepository


class AnalyticsNotReadyError(ServiceUnavailableError):
    """Raised when analytics metadata or mart data is not ready."""
    error_code = "ANALYTICS_NOT_READY"


class InvalidAnalyticsQueryError(ValidationError):
    """Raised when analytics query parameters are invalid."""

    error_code = "INVALID_QUERY"


class AnalyticsService:
    def __init__(self):
        self.repo = AnalyticsRepository()

    async def _get_metadata_or_raise(self, store_id: str) -> Dict[str, Any]:
        """Fetch metadata, raising AnalyticsNotReadyError if not found."""
        metadata = await self.repo.get_analytics_metadata(store_id)
        if not metadata:
            raise AnalyticsNotReadyError(
                "Analytics data is not ready yet.",
                details={"store_id": store_id}
            )
        return metadata

    def _format_freshness(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract freshness fields for shared response."""
        # Convert timestamp to ISO format if it's a Firestore DatetimeWithNanoseconds
        updated_at = metadata.get("analytics_last_updated_at")
        if hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()
        elif updated_at is not None:
            updated_at = str(updated_at)
            
        return {
            "analytics_last_updated_at": updated_at,
            "freshness_status": metadata.get("freshness_status", "stale"),
        }

    async def get_dashboard_summary(self, store_id: str) -> Dict[str, Any]:
        metadata = await self._get_metadata_or_raise(store_id)
        summary = await self.repo.get_dashboard_summary(store_id)
        if not summary:
            raise AnalyticsNotReadyError(
                "Dashboard summary data is not available.",
                details={"store_id": store_id}
            )

        response = self._format_freshness(metadata)
        response["summary"] = summary
        return response

    async def get_sales_trends(
        self,
        store_id: str,
        range_value: str = "30d",
        granularity: str = "daily",
    ) -> Dict[str, Any]:
        allowed_ranges = {"7d": 7, "30d": 30, "90d": 90}
        allowed_granularities = {"daily", "weekly"}
        if range_value not in allowed_ranges:
            raise InvalidAnalyticsQueryError(
                "Invalid `range` value.",
                details={"range": range_value, "allowed": sorted(allowed_ranges.keys())},
            )
        if granularity not in allowed_granularities:
            raise InvalidAnalyticsQueryError(
                "Invalid `granularity` value.",
                details={
                    "granularity": granularity,
                    "allowed": sorted(allowed_granularities),
                },
            )

        metadata = await self._get_metadata_or_raise(store_id)
        points = await self.repo.get_sales_trends(
            store_id=store_id,
            range_days=allowed_ranges[range_value],
            granularity=granularity,
        )
        
        response = self._format_freshness(metadata)
        response["points"] = points
        return response

    async def get_product_performance(self, store_id: str) -> Dict[str, Any]:
        metadata = await self._get_metadata_or_raise(store_id)
        items = await self.repo.get_product_performance(store_id)
        
        response = self._format_freshness(metadata)
        response["items"] = items
        return response

    async def get_customer_insights(self, store_id: str) -> Dict[str, Any]:
        metadata = await self._get_metadata_or_raise(store_id)
        top_customers = await self.repo.get_customer_insights(store_id)
        if not top_customers:
            raise AnalyticsNotReadyError(
                "Customer insights data is not available.",
                details={"store_id": store_id}
            )
        
        response = self._format_freshness(metadata)
        response["top_customers"] = top_customers
        return response
