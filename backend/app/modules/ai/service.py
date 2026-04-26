"""
AI Module – Service layer.

Contains all business logic for the AI chat feature:
  1. Build a deterministic, structured context from analytics, alerts, and inventory.
  2. Send a grounded prompt to the Gemini API (no vector DB, no heavy RAG).
  3. Run a response guard to strip unsupported claims and add freshness warnings.
  4. Persist the user question and AI answer to Firestore chat history.
  5. Return the answer and grounding metadata.

Rules (ai_implementation.md §8):
  - Never invent reasons, trends, or product details not in the provided context.
  - Always mention freshness when analytics is delayed or stale.
  - Use structured system data only — no raw database dumps to Gemini.
  - If context is not ready, raise AI_CONTEXT_NOT_READY (503).
  - If Gemini call fails, raise AI_PROVIDER_ERROR (503).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import google.generativeai as genai

from app.common.config import get_settings
from app.common.exceptions import NotFoundError, ServiceUnavailableError
from app.modules.ai import repository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain errors
# ---------------------------------------------------------------------------

class AIContextNotReadyError(ServiceUnavailableError):
    """Raised when analytics metadata is missing and context cannot be built."""
    error_code = "AI_CONTEXT_NOT_READY"


class AIProviderError(ServiceUnavailableError):
    """Raised when the Gemini API call fails."""
    error_code = "AI_PROVIDER_ERROR"


class ChatSessionNotFoundError(NotFoundError):
    """Raised when the requested chat session does not exist."""
    error_code = "CHAT_SESSION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Gemini client (lazy singleton)
# ---------------------------------------------------------------------------

_gemini_configured = False


def _get_gemini_model() -> genai.GenerativeModel:
    """Configure the Gemini SDK once and return the GenerativeModel instance."""
    global _gemini_configured
    settings = get_settings()

    if not _gemini_configured:
        if settings.gemini_api_key:
            genai.configure(api_key=settings.gemini_api_key)
        else:
            logger.warning(
                "GEMINI_API_KEY is not set. AI calls will fail unless running with ADC."
            )
        _gemini_configured = True

    return genai.GenerativeModel("gemini-1.5-flash")


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

_SYSTEM_INSTRUCTION = """You are RetailMind AI, a business intelligence assistant for a retail store.
Your role is to answer the store owner's questions using ONLY the structured data provided in the context below.

Rules you MUST follow:
1. Only use facts that are explicitly present in the provided context.
2. Never invent sales figures, product details, trends, or reasons not in the context.
3. If analytics data is stale or delayed, clearly mention it in your answer.
4. Keep answers concise, factual, and actionable for a store owner.
5. If you cannot answer from the provided context, say so clearly.
"""


def _build_context_block(
    analytics_summary: str,
    alerts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
) -> str:
    """
    Build the strict JSON-shaped context block required by ai_system_design.md.
    Only compact, approved fields are included.
    """
    payload = {
        "analytics_summary": analytics_summary,
        "alerts": [
            {
                "alert_id": alert.get("alert_id"),
                "alert_type": alert.get("alert_type"),
                "status": alert.get("status"),
                "severity": alert.get("severity"),
                "title": alert.get("title"),
                "message": alert.get("message"),
                "source_entity_id": alert.get("source_entity_id"),
            }
            for alert in alerts
        ],
        "inventory_snapshot": [
            {
                "product_id": product.get("product_id"),
                "name": product.get("name"),
                "quantity_on_hand": product.get("quantity_on_hand"),
                "expiry_date": product.get("expiry_date"),
                "expiry_status": product.get("expiry_status"),
            }
            for product in inventory
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _response_guard(
    raw_answer: str,
    freshness_status: str,
) -> str:
    """
    Post-process the Gemini response:
    - Append a freshness notice if data is stale or delayed.
    - Strip any mention of unavailable data sources (basic sanity check).
    """
    answer = raw_answer.strip()

    if freshness_status == "delayed":
        answer += (
            "\n\n⚠️  Note: Analytics data may be slightly behind real-time activity "
            "(freshness status: delayed)."
        )
    elif freshness_status == "stale":
        answer += (
            "\n\n⚠️  Note: Analytics data is not current (freshness status: stale). "
            "This answer uses the latest available snapshot and may miss recent changes."
        )

    return answer


def _extract_grounding(
    alerts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    analytics_used: bool,
) -> dict[str, Any]:
    """Build the grounding metadata object for the API response."""
    return {
        "analytics_used": analytics_used,
        "alerts_used": [a.get("alert_id", "") for a in alerts],
        "inventory_products_used": [p.get("product_id", "") for p in inventory],
    }


def _build_analytics_summary(
    metadata: dict[str, Any],
    analytics_context: dict[str, Any],
) -> str:
    """
    Build the compact `analytics_summary` string expected by ai_system_design.md.
    """
    last_updated = metadata.get("analytics_last_updated_at", "unknown")
    freshness_status = metadata.get("freshness_status", "unknown")

    parts = [
        f"analytics_last_updated_at={last_updated}",
        f"freshness_status={freshness_status}",
    ]

    dashboard = analytics_context.get("dashboard_summary") or {}
    if dashboard:
        parts.extend(
            [
                f"today_sales={dashboard.get('today_sales', 'unknown')}",
                f"today_transactions={dashboard.get('today_transactions', 'unknown')}",
                f"top_selling_product={dashboard.get('top_selling_product', 'unknown')}",
                f"active_alert_count={dashboard.get('active_alert_count', 'unknown')}",
                f"low_stock_count={dashboard.get('low_stock_count', 'unknown')}",
            ]
        )

    sales_trends = analytics_context.get("sales_trends") or []
    if sales_trends:
        latest_day = sales_trends[0]
        parts.append(f"latest_sales_date={latest_day.get('sales_date', 'unknown')}")
        parts.append(f"latest_total_sales={latest_day.get('total_sales', 'unknown')}")
        if len(sales_trends) >= 2:
            previous_day = sales_trends[1]
            latest_total = float(latest_day.get("total_sales", 0) or 0)
            previous_total = float(previous_day.get("total_sales", 0) or 0)
            direction = "flat"
            if latest_total > previous_total:
                direction = "up"
            elif latest_total < previous_total:
                direction = "down"
            parts.append(f"sales_trend_direction={direction}")

    product_performance = analytics_context.get("product_performance") or []
    if product_performance:
        product_bits = []
        for item in product_performance:
            product_bits.append(
                f"{item.get('product_name', item.get('product_id', 'unknown'))}"
                f" qty_sold={item.get('quantity_sold', 'unknown')}"
                f" revenue={item.get('revenue', 'unknown')}"
            )
        parts.append(f"product_performance={' | '.join(product_bits)}")

    customer_insights = analytics_context.get("customer_insights") or []
    if customer_insights:
        customer_bits = []
        for item in customer_insights:
            customer_bits.append(
                f"{item.get('customer_name', item.get('customer_id', 'unknown'))}"
                f" lifetime_spend={item.get('lifetime_spend', 'unknown')}"
                f" visit_count={item.get('visit_count', 'unknown')}"
            )
        parts.append(f"top_customers={'; '.join(customer_bits)}")

    if len(parts) <= 2:
        return ""
    return "; ".join(parts)


_FRESH_MAX_AGE = timedelta(minutes=30)
_DELAYED_MAX_AGE = timedelta(hours=2)
_FRESHNESS_ORDER = {
    "fresh": 0,
    "delayed": 1,
    "stale": 2,
}


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


def _freshness_from_timestamp(updated_at: Optional[datetime]) -> str:
    if updated_at is None:
        return "stale"

    age = datetime.now(timezone.utc) - updated_at
    if age <= timedelta(0):
        return "fresh"
    if age <= _FRESH_MAX_AGE:
        return "fresh"
    if age <= _DELAYED_MAX_AGE:
        return "delayed"
    return "stale"


def _merge_freshness(computed_status: str, metadata_status: Any) -> str:
    candidate = str(metadata_status).strip().lower() if metadata_status is not None else ""
    if candidate not in _FRESHNESS_ORDER:
        return computed_status
    if _FRESHNESS_ORDER[candidate] > _FRESHNESS_ORDER[computed_status]:
        return candidate
    return computed_status


def _resolve_freshness_fields(metadata: dict[str, Any]) -> tuple[str, str]:
    updated_raw = metadata.get("analytics_last_updated_at")
    updated_dt = _to_datetime(updated_raw)
    computed_status = _freshness_from_timestamp(updated_dt)
    freshness_status = _merge_freshness(computed_status, metadata.get("freshness_status"))

    if hasattr(updated_raw, "isoformat"):
        last_updated = updated_raw.isoformat()
    elif updated_raw is None:
        last_updated = "unknown"
    else:
        last_updated = str(updated_raw)

    return last_updated, freshness_status


def _query_mentions_customers(query: str) -> bool:
    customer_keywords = {
        "customer",
        "customers",
        "buyer",
        "buyers",
        "loyal",
        "frequent",
        "repeat",
    }
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in customer_keywords)


def _get_related_product_ids(alerts: list[dict[str, Any]]) -> list[str]:
    return [
        str(alert["source_entity_id"])
        for alert in alerts
        if alert.get("source_entity_id")
    ]


# ---------------------------------------------------------------------------
# Public service methods
# ---------------------------------------------------------------------------

class AIService:
    """Business logic for AI chat functionality."""

    async def chat(
        self,
        store_id: str,
        user_id: str,
        chat_session_id: str,
        query: str,
    ) -> dict[str, Any]:
        """
        Handle a single AI chat turn.

        Flow:
          1. Read analytics_metadata for freshness context.
          2. Fetch active alerts and inventory snapshot.
          3. Build a deterministic structured prompt.
          4. Call Gemini API.
          5. Guard and format the response.
          6. Persist user query + AI answer to Firestore session history.
          7. Return structured response.

        Raises:
            AIContextNotReadyError: If analytics metadata is unavailable.
            AIProviderError:        If the Gemini call fails.
        """
        # Step 1: Freshness metadata
        metadata = await repository.get_analytics_metadata(store_id)
        if metadata is None:
            raise AIContextNotReadyError(
                "Analytics context is not yet available. "
                "Please wait for the data pipeline to complete its first run.",
                details={"store_id": store_id},
            )

        last_updated, freshness_status = _resolve_freshness_fields(metadata)

        # Step 2: Fetch context data
        alerts = await repository.get_relevant_alerts_snapshot(store_id)
        related_product_ids = _get_related_product_ids(alerts)
        inventory = await repository.get_inventory_snapshot(
            store_id,
            product_ids=related_product_ids,
            query_text=query,
        )
        try:
            analytics_context = await repository.get_analytics_context(
                store_id,
                include_customer_insights=_query_mentions_customers(query),
                product_ids=[item.get("product_id") for item in inventory if item.get("product_id")],
            )
        except Exception as exc:
            logger.warning("Analytics context query failed", exc_info=exc)
            raise AIContextNotReadyError(
                "Analytics summary is not yet available. "
                "Please wait for the data pipeline to refresh the mart tables.",
                details={"store_id": store_id},
            )
        analytics_summary = _build_analytics_summary(
            {
                **metadata,
                "analytics_last_updated_at": last_updated,
                "freshness_status": freshness_status,
            },
            analytics_context,
        )
        if not analytics_summary:
            raise AIContextNotReadyError(
                "Analytics summary is not yet available. "
                "Please wait for the data pipeline to refresh the mart tables.",
                details={"store_id": store_id},
            )

        # Step 3: Build prompt
        context_block = _build_context_block(analytics_summary, alerts, inventory)
        full_prompt = (
            f"{_SYSTEM_INSTRUCTION}\n\n"
            f"=== STRUCTURED CONTEXT JSON ===\n{context_block}\n\n"
            f"=== USER QUESTION ===\n{query}"
        )

        # Step 4: Call Gemini
        try:
            model = _get_gemini_model()
            response = model.generate_content(full_prompt)
            raw_answer: str = response.text
        except Exception as exc:
            logger.error("Gemini API call failed", exc_info=exc)
            raise AIProviderError(
                "The AI provider returned an error. Please try again later.",
                details={"error": str(exc)},
            )

        # Step 5: Guard response
        answer = _response_guard(raw_answer, freshness_status)
        grounding = _extract_grounding(alerts, inventory, analytics_used=True)

        # Step 6: Persist messages
        now = datetime.now(tz=timezone.utc)
        existing_session = await repository.get_chat_session(chat_session_id)
        if existing_session is not None and existing_session.get("store_id") != store_id:
            raise ChatSessionNotFoundError(
                f"Chat session '{chat_session_id}' was not found.",
                details={"chat_session_id": chat_session_id},
            )

        await repository.ensure_chat_session(
            chat_session_id=chat_session_id,
            store_id=store_id,
            user_id=user_id,
            updated_at=now,
        )
        await repository.append_message(
            chat_session_id=chat_session_id,
            message_id=f"msg_{uuid.uuid4().hex}",
            role="user",
            text=query,
            created_at=now,
        )
        await repository.append_message(
            chat_session_id=chat_session_id,
            message_id=f"msg_{uuid.uuid4().hex}",
            role="assistant",
            text=answer,
            created_at=now,
        )

        # Step 7: Return
        return {
            "chat_session_id": chat_session_id,
            "analytics_last_updated_at": last_updated,
            "freshness_status": freshness_status,
            "answer": answer,
            "grounding": grounding,
        }

    async def get_session_history(
        self,
        store_id: str,
        chat_session_id: str,
    ) -> dict[str, Any]:
        """
        Return the full message history for a chat session.

        Raises:
            ChatSessionNotFoundError: If the session does not exist in Firestore.
        """
        session = await repository.get_chat_session(chat_session_id)
        if session is None or session.get("store_id") != store_id:
            raise ChatSessionNotFoundError(
                f"Chat session '{chat_session_id}' was not found.",
                details={"chat_session_id": chat_session_id},
            )

        messages = await repository.list_messages(chat_session_id)

        # Shape messages per api_contracts.md §8
        shaped_messages = [
            {
                "role": msg.get("role"),
                "text": msg.get("text"),
                "created_at": msg.get("created_at"),
            }
            for msg in messages
        ]

        return {
            "chat_session_id": chat_session_id,
            "messages": shaped_messages,
        }
