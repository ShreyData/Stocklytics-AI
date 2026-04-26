from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.common.exceptions import ServiceUnavailableError, ValidationError
from app.modules.analytics.repository import AnalyticsRepository


class AnalyticsNotReadyError(ServiceUnavailableError):
    """Raised when analytics metadata or mart data is not ready."""
    error_code = "ANALYTICS_NOT_READY"


class InvalidAnalyticsQueryError(ValidationError):
    """Raised when analytics query parameters are invalid."""

    error_code = "INVALID_QUERY"


class AnalyticsService:
    _FRESH_MAX_AGE = timedelta(minutes=30)
    _DELAYED_MAX_AGE = timedelta(hours=2)
    _FRESHNESS_ORDER = {
        "fresh": 0,
        "delayed": 1,
        "stale": 2,
    }

    def __init__(self):
        self.repo = AnalyticsRepository()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _to_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        if hasattr(value, "seconds"):
            return datetime.fromtimestamp(value.seconds, tz=timezone.utc)
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return None
            if candidate.endswith("Z"):
                candidate = candidate[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(candidate)
            except ValueError:
                return None
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        return None

    def _freshness_from_timestamp(self, updated_at: Optional[datetime]) -> str:
        if updated_at is None:
            return "stale"

        age = self._utcnow() - updated_at
        if age <= timedelta(0):
            return "fresh"
        if age <= self._FRESH_MAX_AGE:
            return "fresh"
        if age <= self._DELAYED_MAX_AGE:
            return "delayed"
        return "stale"

    def _merge_freshness(self, computed_status: str, metadata_status: Any) -> str:
        candidate = str(metadata_status).strip().lower() if metadata_status is not None else ""
        if candidate not in self._FRESHNESS_ORDER:
            return computed_status
        return candidate if self._FRESHNESS_ORDER[candidate] > self._FRESHNESS_ORDER[computed_status] else computed_status

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
        updated_raw = metadata.get("analytics_last_updated_at")
        updated_dt = self._to_datetime(updated_raw)
        computed_status = self._freshness_from_timestamp(updated_dt)
        final_status = self._merge_freshness(computed_status, metadata.get("freshness_status"))

        if hasattr(updated_raw, "isoformat"):
            updated_at = updated_raw.isoformat()
        elif updated_raw is None:
            updated_at = None
        else:
            updated_at = str(updated_raw)

        return {
            "analytics_last_updated_at": updated_at,
            "freshness_status": final_status,
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

        response = self._format_freshness(metadata)
        response["top_customers"] = top_customers
        return response
