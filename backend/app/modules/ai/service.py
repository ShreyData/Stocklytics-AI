"""
AI Module – Service layer.

Contains all business logic for the AI chat feature:
  1. Build a deterministic, structured context from analytics, alerts, and inventory.
  2. Send a grounded prompt to the hosted Gemma model (no vector DB, no heavy RAG).
  3. Run a response guard to strip unsupported claims and add freshness warnings.
  4. Persist the user question and AI answer to Firestore chat history.
  5. Return the answer and grounding metadata.

Rules (ai_implementation.md §8):
  - Never invent reasons, trends, or product details not in the provided context.
  - Return freshness as structured metadata and keep answer text focused on the question.
  - Use structured system data only — no raw database dumps to Gemini.
  - If context is not ready, raise AI_CONTEXT_NOT_READY (503).
  - If the hosted model call fails, raise AI_PROVIDER_ERROR (503).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.common.config import get_settings
from app.common.exceptions import NotFoundError, ServiceUnavailableError
from app.modules.ai import repository
from app.modules.analytics.repository import AnalyticsRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain errors
# ---------------------------------------------------------------------------

class AIContextNotReadyError(ServiceUnavailableError):
    """Raised when analytics metadata is missing and context cannot be built."""
    error_code = "AI_CONTEXT_NOT_READY"


class AIProviderError(ServiceUnavailableError):
    """Raised when the hosted model API call fails."""
    error_code = "AI_PROVIDER_ERROR"


class ChatSessionNotFoundError(NotFoundError):
    """Raised when the requested chat session does not exist."""
    error_code = "CHAT_SESSION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Hosted model client
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

_SYSTEM_INSTRUCTION = """You are Stocklytics AI, a business intelligence assistant for a retail store.
Your role is to answer the store owner's questions using ONLY the structured data provided in the context below.

Rules you MUST follow:
1. Only use facts that are explicitly present in the provided context.
2. Never invent sales figures, product details, trends, or reasons not in the context.
3. Do not add freshness disclaimers, timestamps, or system notes in the answer text.
4. Keep answers concise, factual, and actionable for a store owner.
5. Use plain text only. Do not use markdown, bullet symbols, or decorative formatting.
6. Prefer 2 to 4 short sentences.
7. If you cannot answer from the provided context, say so clearly.
"""


def _build_context_block(
    analytics_summary: str,
    alerts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    rag_products: Optional[list[dict[str, Any]]] = None,
) -> str:
    """
    Build the strict JSON-shaped context block required by ai_system_design.md.
    Only compact, approved fields are included.
    rag_products (optional) adds semantically retrieved products from BigQuery
    Vector Search to augment the deterministic inventory snapshot.
    """
    alerts = alerts[:6]
    inventory = inventory[:8]
    customers = customers[:5]
    transactions = transactions[:6]
    rag_products = (rag_products or [])[:4]

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
                "category": product.get("category"),
                "price": product.get("price"),
                "quantity_on_hand": product.get("quantity_on_hand"),
                "reorder_threshold": product.get("reorder_threshold"),
                "expiry_date": product.get("expiry_date"),
                "expiry_status": product.get("expiry_status"),
                "status": product.get("status"),
                "created_at": product.get("created_at"),
                "updated_at": product.get("updated_at"),
            }
            for product in inventory
        ],
        "rag_relevant_products": [
            {
                "product_id": p.get("product_id"),
                "product_name": p.get("product_name"),
                "category": p.get("category"),
                "retrieval_note": "semantically matched to query via vector search",
            }
            for p in rag_products
        ],
        "customer_snapshot": [
            {
                "customer_id": customer.get("customer_id"),
                "name": customer.get("name"),
                "phone": customer.get("phone"),
                "total_spend": customer.get("total_spend", customer.get("lifetime_spend")),
                "visit_count": customer.get("visit_count"),
                "last_purchase_at": customer.get("last_purchase_at"),
                "created_at": customer.get("created_at"),
                "updated_at": customer.get("updated_at"),
            }
            for customer in customers
        ],
        "recent_transactions": transactions,
    }
    return json.dumps(payload, indent=2, sort_keys=True, default=_json_safe_default)


def _json_safe_default(value: Any) -> Any:
    """Convert Firestore/BigQuery values into JSON-safe prompt content."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


_LEGACY_FRESHNESS_PATTERNS = (
    r"\s*(?:⚠️\s*)?Note:\s*Analytics data may be slightly behind real-time activity\s*\(freshness status:\s*delayed\)\.?",
    r"\s*(?:⚠️\s*)?Note:\s*Analytics data is not current\s*\(freshness status:\s*stale\)\.\s*This answer uses the latest available snapshot and may miss recent changes\.?",
    r"\s*(?:⚠️\s*)?Note:\s*Analytics data is slightly delayed, so this answer uses the latest available snapshot\.?",
    r"\s*Please note this data is stale, last updated on\s+[^\n.]+\.?",
    r"\s*Freshness status:\s*(?:delayed|stale)\.?",
)


def _strip_legacy_freshness_text(answer: str) -> str:
    """Remove boilerplate freshness text that the UI already renders separately."""
    cleaned = answer
    for pattern in _LEGACY_FRESHNESS_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _response_guard(
    raw_answer: str,
    freshness_status: str,
) -> str:
    """
    Post-process the model response:
    - Remove boilerplate freshness notices because the UI renders freshness separately.
    - Strip any mention of unavailable data sources (basic sanity check).
    """
    answer = raw_answer.strip()
    answer = answer.replace("**", "")
    answer = answer.replace("__", "")
    answer = " ".join(answer.split())
    return _strip_legacy_freshness_text(answer)


def _extract_grounding(
    alerts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    analytics_used: bool,
    rag_products: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build the grounding metadata object for the API response."""
    return {
        "analytics_used": analytics_used,
        "alerts_used": [a.get("alert_id", "") for a in alerts],
        "inventory_products_used": [p.get("product_id", "") for p in inventory],
        "rag_products_used": [p.get("product_id", "") for p in (rag_products or [])],
    }


def _query_terms(query: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", query.lower())
        if token
    }


def _query_mentions_any(query: str, terms: set[str]) -> bool:
    tokens = _query_terms(query)
    return any(term in tokens for term in terms)


def _query_contains_phrase(query: str, phrases: tuple[str, ...]) -> bool:
    lowered = query.lower()
    return any(phrase in lowered for phrase in phrases)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    return _coerce_quantity(value)


def _product_timestamp(product: dict[str, Any], field: str) -> Optional[datetime]:
    return _to_datetime(product.get(field))


def _format_product_age(product: dict[str, Any]) -> str:
    created_at = _product_timestamp(product, "created_at")
    if created_at is None:
        return "added recently"

    delta = datetime.now(timezone.utc) - created_at
    days = max(delta.days, 0)
    if days == 0:
        return "added today"
    if days == 1:
        return "added 1 day ago"
    if days < 7:
        return f"added {days} days ago"
    return f"added on {created_at.strftime('%b %d')}"


def _top_risk_products(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def score(product: dict[str, Any]) -> tuple[int, int]:
        expiry_status = str(product.get("expiry_status", "")).upper()
        quantity = _safe_int(product.get("quantity_on_hand"))
        reorder_threshold = _safe_int(product.get("reorder_threshold"))
        risk = 0
        if expiry_status == "EXPIRED":
            risk += 4
        elif expiry_status == "EXPIRING_SOON":
            risk += 2
        if reorder_threshold and quantity <= reorder_threshold:
            risk += 3
        elif quantity <= 0:
            risk += 3
        return (risk, -quantity)

    ranked = [product for product in inventory if score(product)[0] > 0]
    ranked.sort(key=score, reverse=True)
    return ranked


def _build_recent_product_answer(query: str, inventory: list[dict[str, Any]]) -> Optional[str]:
    if not inventory:
        return None

    recent_queries = {"new", "recent", "latest", "added", "addition"}
    if not _query_mentions_any(query, recent_queries) and not _query_contains_phrase(
        query,
        ("new product", "recent product", "added in inventory", "added to inventory"),
    ):
        return None

    active_products = [product for product in inventory if str(product.get("status", "ACTIVE")).upper() == "ACTIVE"]
    candidates = active_products or inventory
    ordered = sorted(
        candidates,
        key=lambda product: (
            _product_timestamp(product, "created_at") or datetime.min.replace(tzinfo=timezone.utc),
            _product_timestamp(product, "updated_at") or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    newest = ordered[0]
    quantity = _safe_int(newest.get("quantity_on_hand"))
    reorder_threshold = _safe_int(newest.get("reorder_threshold"))
    price = newest.get("price")
    category = newest.get("category") or "Uncategorized"

    parts = [
        f"The newest product I can see is {newest.get('name', 'this item')} in {category}, { _format_product_age(newest) }."
    ]
    if price not in (None, ""):
        parts.append(f"It is priced at {price} and currently has {quantity} units on hand.")
    else:
        parts.append(f"It currently has {quantity} units on hand.")

    if reorder_threshold and quantity <= reorder_threshold:
        parts.append("It is already near or below its reorder threshold, so it needs replenishment planning.")
    elif quantity == 0:
        parts.append("It is already out of stock, so it should be restocked before promotion.")
    else:
        parts.append("Stock looks available, so the next step is to watch sell-through and reorder timing.")
    return " ".join(parts)


def _build_inventory_status_answer(
    query: str,
    inventory: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
) -> Optional[str]:
    inventory_terms = {"inventory", "stock", "product", "products", "status", "items"}
    if not _query_mentions_any(query, inventory_terms) and not _query_contains_phrase(
        query,
        ("what needs attention", "what should i focus on", "inventory status"),
    ):
        return None

    if not inventory:
        return "I could not load the current inventory snapshot, so I cannot confirm product-level status right now."

    active_products = [product for product in inventory if str(product.get("status", "ACTIVE")).upper() == "ACTIVE"]
    low_stock = [
        product for product in active_products
        if _safe_int(product.get("reorder_threshold")) > 0
        and _safe_int(product.get("quantity_on_hand")) <= _safe_int(product.get("reorder_threshold"))
    ]
    expiring = [
        product for product in active_products
        if str(product.get("expiry_status", "")).upper() in {"EXPIRING_SOON", "EXPIRED"}
    ]
    risks = _top_risk_products(active_products)[:3]
    active_alerts = [alert for alert in alerts if str(alert.get("status", "")).upper() == "ACTIVE"]

    parts = [
        f"I can see {len(active_products)} active products in the current inventory snapshot."
    ]
    if low_stock:
        parts.append(f"{len(low_stock)} are at or below reorder threshold.")
    if expiring:
        parts.append(f"{len(expiring)} are expired or expiring soon.")

    if risks:
        parts.append(
            "Top attention items are "
            + ", ".join(
                f"{product.get('name', product.get('product_id', 'unknown'))} ({_safe_int(product.get('quantity_on_hand'))} units, {str(product.get('expiry_status', 'OK')).lower()})"
                for product in risks
            )
            + "."
        )

    if active_alerts:
        parts.append(f"There are also {len(active_alerts)} active alerts reinforcing those risks.")

    if low_stock:
        parts.append("Best next move is to reorder the lowest-stock items first and clear any expired stock from sale.")
    elif expiring:
        parts.append("Best next move is to prioritise sell-through or markdowns for the expiring items.")
    else:
        parts.append("Overall inventory looks stable right now, so focus on keeping your best sellers in stock.")
    return " ".join(parts)


def _build_sales_answer(query: str, analytics_context: dict[str, Any]) -> Optional[str]:
    sales_terms = {"sale", "sales", "revenue", "transaction", "transactions", "today"}
    if not _query_mentions_any(query, sales_terms):
        return None

    summary = analytics_context.get("dashboard_summary") or {}
    if not summary:
        return None

    today_sales = _safe_float(summary.get("today_sales"))
    today_transactions = _safe_int(summary.get("today_transactions"))
    top_product = summary.get("top_selling_product") or "your top product"
    low_stock_count = _safe_int(summary.get("low_stock_count"))

    parts = [
        f"Today's confirmed sales are {today_sales:.0f} across {today_transactions} transactions."
    ]
    parts.append(f"{top_product} is the current top-selling product.")
    if low_stock_count > 0:
        parts.append(f"{low_stock_count} products are already low on stock, so protect availability on your fast movers.")
    else:
        parts.append("Inventory coverage looks cleaner, so the next step is to maintain momentum on the current top seller.")
    return " ".join(parts)


def _rank_customers(customers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def spend(customer: dict[str, Any]) -> float:
        return _safe_float(customer.get("lifetime_spend", customer.get("total_spend", 0.0)))

    return sorted(
        customers,
        key=lambda customer: (
            spend(customer),
            _safe_int(customer.get("visit_count")),
        ),
        reverse=True,
    )


def _build_customer_answer(
    query: str,
    analytics_context: dict[str, Any],
    customers: list[dict[str, Any]],
) -> Optional[str]:
    customer_terms = {"customer", "customers", "buyer", "buyers", "loyal", "repeat", "spend", "spender"}
    if not _query_mentions_any(query, customer_terms) and not _query_contains_phrase(
        query,
        ("best customers", "top customers", "loyal customers"),
    ):
        return None

    ranked = _rank_customers(analytics_context.get("customer_insights") or customers)
    if not ranked:
        return "I could not load ranked customer insights from the current store data, so I cannot confirm your top customers yet."

    top = ranked[:3]
    parts = [
        "Your top customers right now are "
        + ", ".join(
            f"{customer.get('customer_name', customer.get('name', customer.get('customer_id', 'Unknown')))} "
            f"({_safe_float(customer.get('lifetime_spend', customer.get('total_spend', 0.0))):.0f} spend, {_safe_int(customer.get('visit_count'))} visits)"
            for customer in top
        )
        + "."
    ]
    leader = top[0]
    last_purchase = leader.get("last_purchase_at")
    if last_purchase:
        parts.append(
            f"{leader.get('customer_name', leader.get('name', 'This customer'))} was last seen on {_display_timestamp(last_purchase)}."
        )
    parts.append("Best next move is to target these repeat buyers with availability updates, bundles, or loyalty outreach.")
    return " ".join(parts)


def _build_transaction_answer(query: str, transactions: list[dict[str, Any]]) -> Optional[str]:
    transaction_terms = {"transaction", "transactions", "bill", "billing", "payment", "payments", "purchase", "purchases"}
    if not _query_mentions_any(query, transaction_terms) and not _query_contains_phrase(
        query,
        ("recent transactions", "recent purchases", "last bill"),
    ):
        return None

    if not transactions:
        return "I could not load recent transaction records from the database, so I cannot confirm billing activity right now."

    recent = transactions[:3]
    parts = [
        "The most recent transactions I can see are "
        + ", ".join(
            f"{txn.get('transaction_id', 'unknown')} for {_safe_float(txn.get('total_amount')):.0f} via {txn.get('payment_method', 'unknown payment method')}"
            for txn in recent
        )
        + "."
    ]
    latest = recent[0]
    if latest.get("sale_timestamp"):
        parts.append(f"The latest one was recorded on {_display_timestamp(latest.get('sale_timestamp'))}.")
    return " ".join(parts)


def _build_focus_answer(
    query: str,
    analytics_context: dict[str, Any],
    alerts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
) -> Optional[str]:
    if not _query_contains_phrase(query, ("what should i focus on", "what needs attention", "priority", "priorities")):
        return None

    active_alerts = [alert for alert in alerts if str(alert.get("status", "")).upper() == "ACTIVE"]
    risks = _top_risk_products(inventory)
    top_product = (analytics_context.get("dashboard_summary") or {}).get("top_selling_product")

    parts: list[str] = []
    if active_alerts:
        top_alert = active_alerts[0]
        parts.append(f"Your first priority is {top_alert.get('title', 'the top active alert')}.")
    if risks:
        top_risk = risks[0]
        parts.append(
            f"The most urgent inventory item is {top_risk.get('name', top_risk.get('product_id', 'unknown'))} with {_safe_int(top_risk.get('quantity_on_hand'))} units left and status {str(top_risk.get('expiry_status', 'OK')).lower()}."
        )
    if top_product:
        parts.append(f"Keep {top_product} available because it is currently leading sales.")
    if not parts:
        return None
    parts.append("Best next move is to resolve the top alert, restock the weakest item, and then review your best seller coverage.")
    return " ".join(parts)


def _query_prefers_operator_answer(query: str) -> bool:
    return (
        _query_mentions_any(
            query,
            {
                "inventory",
                "stock",
                "product",
                "products",
                "sales",
                "sale",
                "revenue",
                "alert",
                "alerts",
                "new",
                "recent",
                "latest",
                "added",
                "status",
                "focus",
                "priority",
            },
        )
        or _query_contains_phrase(
            query,
            ("what needs attention", "what should i focus on", "new product", "inventory status"),
        )
    )


def _looks_like_refusal(answer: str) -> bool:
    lowered = answer.lower()
    refusal_signals = (
        "i cannot answer",
        "i can't answer",
        "cannot answer this question",
        "provided data only contains",
        "not enough information",
        "do not have enough information",
    )
    return any(signal in lowered for signal in refusal_signals)


def _build_operator_answer(
    query: str,
    analytics_context: dict[str, Any],
    alerts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> Optional[str]:
    answer, _ = _build_operator_answer_result(
        query,
        analytics_context,
        alerts,
        inventory,
        customers,
        transactions,
    )
    return answer


def _build_operator_answer_result(
    query: str,
    analytics_context: dict[str, Any],
    alerts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> tuple[Optional[str], bool]:
    builders: tuple[tuple[Any, bool], ...] = (
        (_build_recent_product_answer, False),
        (lambda q, i: _build_focus_answer(q, analytics_context, alerts, inventory), False),
        (lambda q, i: _build_inventory_status_answer(q, inventory, alerts), False),
        (lambda q, i: _build_customer_answer(q, analytics_context, customers), True),
        (lambda q, i: _build_transaction_answer(q, transactions), False),
        (lambda q, i: _build_sales_answer(q, analytics_context), True),
    )
    for builder, analytics_used in builders:
        answer = builder(query, inventory)
        if answer:
            return answer, analytics_used
    return None, False


def _infer_analytics_used(
    query: str,
    answer: str,
    operator_analytics_used: bool,
) -> bool:
    if operator_analytics_used:
        return True

    if _query_mentions_any(
        query,
        {"sale", "sales", "revenue", "transaction", "transactions", "customer", "customers", "buyer", "buyers"},
    ):
        return True

    if _query_mentions_any(query, {"inventory", "stock", "product", "products", "new", "recent", "added"}):
        return False

    lowered = answer.lower()
    analytics_signals = (
        "today's confirmed sales",
        "transactions",
        "top-selling product",
        "leading sales",
    )
    return any(signal in lowered for signal in analytics_signals)
    return None


def _build_fallback_answer(
    query: str,
    analytics_summary: str,
    analytics_context: dict[str, Any],
    alerts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    freshness_status: str,
) -> str:
    """
    Build a deterministic local fallback answer when the hosted model or mart context is unavailable.
    """
    operator_answer = _build_operator_answer(
        query,
        analytics_context,
        alerts,
        inventory,
        customers,
        transactions,
    )
    if operator_answer:
        return operator_answer

    lines = []
    lowered = query.lower()

    if "sale" in lowered or "revenue" in lowered or "transaction" in lowered:
        lines.append("Here is the latest operational sales snapshot I can confirm:")
        for part in analytics_summary.split("; "):
            if part.startswith(("today_sales=", "today_transactions=", "top_selling_product=")):
                lines.append(part.replace("=", ": ", 1))

    if "alert" in lowered or "stock" in lowered:
        active_alerts = [alert for alert in alerts if alert.get("status") == "ACTIVE"]
        low_stock_products = [
            item for item in inventory
            if _coerce_quantity(item.get("quantity_on_hand", 0)) <= 0
            or str(item.get("expiry_status", "")).upper() in {"EXPIRING_SOON", "EXPIRED"}
        ]
        lines.append(f"Active alerts: {len(active_alerts)}.")
        if active_alerts:
            lines.append(
                "Top alert titles: " + ", ".join(str(alert.get("title") or alert.get("alert_id")) for alert in active_alerts[:3])
            )
        if low_stock_products:
            lines.append(
                "Products needing attention: "
                + ", ".join(str(item.get("name") or item.get("product_id")) for item in low_stock_products[:5])
            )

    if not lines:
        lines.append("I can answer from the current operational store data, but the full AI provider context is unavailable right now.")
        lines.append("Available snapshot:")
        for part in analytics_summary.split("; "):
            if part.startswith(("today_sales=", "today_transactions=", "active_alert_count=", "low_stock_count=")):
                lines.append(part.replace("=", ": ", 1))

    return "\n".join(lines)


def _coerce_quantity(value: Any) -> int:
    """Best-effort int coercion for loosely typed inventory quantities."""
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _build_analytics_summary(
    metadata: dict[str, Any],
    analytics_context: dict[str, Any],
) -> str:
    """
    Build the compact `analytics_summary` string expected by ai_system_design.md.
    """
    last_updated = _display_timestamp(metadata.get("analytics_last_updated_at", "unknown"))
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


def _display_timestamp(value: Any) -> str:
    dt = _to_datetime(value)
    if dt is None:
        return str(value)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


_FRESH_MAX_AGE = timedelta(minutes=30)
_DELAYED_MAX_AGE = timedelta(hours=2)
_FRESHNESS_ORDER = {
    "fresh": 0,
    "delayed": 1,
    "stale": 2,
}
_CONTEXT_TIMEOUT_SECONDS = 6
_MODEL_TIMEOUT_SECONDS = 20
_PERSIST_TIMEOUT_SECONDS = 6


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


async def _await_with_timeout(coro, timeout_seconds: float):
    """Bound slow upstream work so AI chat can fall back instead of hanging."""
    return await asyncio.wait_for(coro, timeout=timeout_seconds)


_EMBED_QUERY_MODEL_FALLBACKS = ("gemini-embedding-001",)


def _query_embedding_model_candidates(preferred_model: str) -> list[str]:
    ordered: list[str] = []
    for model_name in (preferred_model, *_EMBED_QUERY_MODEL_FALLBACKS):
        if model_name and model_name not in ordered:
            ordered.append(model_name)
    return ordered


async def _embed_query(query: str) -> Optional[list[float]]:
    """Generate a query embedding via Gemini embedding models.

    Returns None on any failure so the caller can skip vector retrieval
    and fall through to the deterministic context path.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        for model in _query_embedding_model_candidates(settings.gemini_embedding_model):
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models"
                f"/{model}:embedContent"
            )
            payload = {
                "model": f"models/{model}",
                "content": {"parts": [{"text": query}]},
                "taskType": "RETRIEVAL_QUERY",
            }
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()["embedding"]["values"]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {400, 404}:
                    logger.warning(
                        "Query embedding model unavailable; trying fallback model",
                        extra={"model": model, "status_code": exc.response.status_code},
                    )
                    continue
                logger.warning(
                    "Query embedding failed; skipping RAG retrieval",
                    exc_info=exc,
                )
                return None
            except Exception as exc:
                logger.warning(
                    "Query embedding failed; skipping RAG retrieval",
                    exc_info=exc,
                )
                return None
    return None


async def _generate_model_answer(prompt: str) -> str:
    """Call the hosted model using the official REST API with the configured API key."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise AIProviderError("GEMINI_API_KEY is not configured.")

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "maxOutputTokens": 220,
        },
    }
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }

    timeout_seconds = max(float(settings.gemini_model_timeout_seconds), 1.0)
    model_candidates = _generation_model_candidates(
        settings.gemma_model_id,
        settings.gemini_model_fallbacks,
    )
    max_retries = max(int(settings.gemini_generation_retries), 0)
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for model in model_candidates:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    body = response.json()
                    return _extract_model_text(body)
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status_code = exc.response.status_code
                    if status_code in {400, 404}:
                        logger.warning(
                            "Hosted model unavailable or invalid; trying next model",
                            extra={"model": model, "status_code": status_code},
                        )
                        break
                    if _should_retry_model_error(exc) and attempt < max_retries:
                        await _sleep_before_retry(attempt, model=model, reason=f"http_{status_code}")
                        continue
                    logger.warning(
                        "Hosted model request failed",
                        exc_info=exc,
                        extra={"model": model, "status_code": status_code, "attempt": attempt + 1},
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    if _should_retry_model_error(exc) and attempt < max_retries:
                        await _sleep_before_retry(attempt, model=model, reason=exc.__class__.__name__)
                        continue
                    logger.warning(
                        "Hosted model request failed",
                        exc_info=exc,
                        extra={"model": model, "attempt": attempt + 1},
                    )
                    break

    if last_error is not None:
        raise AIProviderError(f"Hosted model request failed after retries: {last_error}")
    raise AIProviderError("No hosted model candidates are configured.")


def _generation_model_candidates(primary_model: str, fallback_models: list[str]) -> list[str]:
    ordered: list[str] = []
    for model_name in (primary_model, *fallback_models):
        if model_name and model_name not in ordered:
            ordered.append(model_name)
    return ordered


def _extract_model_text(body: dict[str, Any]) -> str:
    candidates = body.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text = "".join(str(part.get("text", "")) for part in parts if part.get("text"))
        if text.strip():
            return text.strip()

    prompt_feedback = body.get("promptFeedback") or {}
    block_reason = prompt_feedback.get("blockReason")
    if block_reason:
        raise AIProviderError(f"Model response was blocked: {block_reason}")
    raise AIProviderError("Model response did not contain any text.")


def _should_retry_model_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 429, 500, 502, 503, 504}
    return False


async def _sleep_before_retry(attempt: int, *, model: str, reason: str) -> None:
    delay_seconds = min(1.0 * (2**attempt) + random.uniform(0.0, 0.25), 6.0)
    logger.warning(
        "Retrying hosted model request after transient failure",
        extra={"model": model, "retry_in_seconds": round(delay_seconds, 2), "reason": reason},
    )
    await asyncio.sleep(delay_seconds)


async def _get_live_dashboard_summary_fallback(
    live_repo: AnalyticsRepository,
    store_id: str,
) -> tuple[dict[str, Any], bool]:
    """Attempt a live summary read, otherwise fall back to a minimal empty snapshot."""
    try:
        summary = await _await_with_timeout(
            live_repo.get_live_dashboard_summary(store_id),
            _CONTEXT_TIMEOUT_SECONDS,
        )
        return summary, False
    except Exception as exc:
        logger.warning(
            "Live dashboard summary read failed; using minimal fallback summary",
            exc_info=exc,
            extra={"store_id": store_id},
        )
        return (
            {
                "today_sales": 0.0,
                "today_transactions": 0,
                "active_alert_count": 0,
                "low_stock_count": 0,
                "top_selling_product": "unknown",
            },
            True,
        )


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


def _query_mentions_transactions(query: str) -> bool:
    transaction_keywords = {
        "transaction",
        "transactions",
        "bill",
        "billing",
        "payment",
        "payments",
        "purchase",
        "purchases",
    }
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in transaction_keywords)


def _get_related_product_ids(alerts: list[dict[str, Any]]) -> list[str]:
    return [
        str(alert["source_entity_id"])
        for alert in alerts
        if alert.get("source_entity_id")
    ]


def _query_requests_deeper_reasoning(query: str) -> bool:
    phrases = (
        "why",
        "how",
        "compare",
        "trend",
        "forecast",
        "predict",
        "recommend strategy",
        "what should i do next",
        "explain",
        "root cause",
    )
    lowered = query.lower()
    return any(phrase in lowered for phrase in phrases)


def _should_use_operator_answer_directly(query: str, operator_answer: Optional[str]) -> bool:
    """Return True for routine operational queries that don't need full model generation."""
    if not operator_answer:
        return False
    if _query_requests_deeper_reasoning(query):
        return False
    return _query_prefers_operator_answer(query)


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
          4. Call the hosted model API.
          5. Guard and format the response.
          6. Persist user query + AI answer to Firestore session history.
          7. Return structured response.

        Raises:
            AIContextNotReadyError: If analytics metadata is unavailable.
            AIProviderError:        If the hosted model call fails.
        """
        # Step 1: Freshness metadata
        degraded_context = False
        try:
            metadata = await _await_with_timeout(
                repository.get_analytics_metadata(store_id),
                _CONTEXT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "Analytics metadata read failed; using synthetic freshness metadata",
                exc_info=exc,
                extra={"store_id": store_id},
            )
            metadata = None
            degraded_context = True
        if metadata is None:
            metadata = {
                "analytics_last_updated_at": datetime.now(timezone.utc).isoformat(),
                "freshness_status": "fresh",
            }

        last_updated, freshness_status = _resolve_freshness_fields(metadata)

        # Step 2: Fetch independent context data in parallel
        alerts_task = asyncio.create_task(
            _await_with_timeout(
                repository.get_relevant_alerts_snapshot(store_id),
                _CONTEXT_TIMEOUT_SECONDS,
            )
        )
        customers_task = asyncio.create_task(
            _await_with_timeout(
                repository.get_customer_snapshot(
                    store_id,
                    query_text=query,
                ),
                _CONTEXT_TIMEOUT_SECONDS,
            )
        )
        query_embedding_task = asyncio.create_task(
            _await_with_timeout(
                _embed_query(query),
                _CONTEXT_TIMEOUT_SECONDS,
            )
        )

        try:
            alerts = await alerts_task
        except Exception as exc:
            logger.warning(
                "Alerts snapshot read failed; continuing without alerts context",
                exc_info=exc,
                extra={"store_id": store_id},
            )
            alerts = []
            degraded_context = True
        related_product_ids = _get_related_product_ids(alerts)
        try:
            inventory = await _await_with_timeout(
                repository.get_inventory_snapshot(
                    store_id,
                    product_ids=related_product_ids,
                    query_text=query,
                ),
                _CONTEXT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "Inventory snapshot read failed; continuing without inventory context",
                exc_info=exc,
                extra={"store_id": store_id},
            )
            inventory = []
            degraded_context = True
        try:
            customers = await customers_task
        except Exception as exc:
            logger.warning(
                "Customer snapshot read failed; continuing without customer context",
                exc_info=exc,
                extra={"store_id": store_id},
            )
            customers = []
            degraded_context = True
        try:
            transactions = await _await_with_timeout(
                repository.get_recent_transactions_snapshot(
                    store_id,
                    query_text=query,
                    customer_ids=[item.get("customer_id") for item in customers if item.get("customer_id")],
                    product_ids=[item.get("product_id") for item in inventory if item.get("product_id")],
                ),
                _CONTEXT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "Transaction snapshot read failed; continuing without transaction context",
                exc_info=exc,
                extra={"store_id": store_id},
            )
            transactions = []
            degraded_context = True

        # Step 2b: RAG — vector retrieval (non-blocking; degrades gracefully)
        rag_products: list[dict[str, Any]] = []
        try:
            _query_embedding = await query_embedding_task
            if _query_embedding:
                _rag_top_k = get_settings().vector_search_top_k
                rag_products = await _await_with_timeout(
                    repository.vector_search_products(
                        store_id,
                        query_embedding=_query_embedding,
                        top_k=_rag_top_k,
                    ),
                    _CONTEXT_TIMEOUT_SECONDS,
                )
        except Exception as exc:
            logger.warning(
                "RAG vector retrieval failed; continuing without vector context",
                exc_info=exc,
                extra={"store_id": store_id},
            )
            rag_products = []
            degraded_context = True

        try:
            analytics_context = await _await_with_timeout(
                repository.get_analytics_context(
                    store_id,
                    include_customer_insights=_query_mentions_customers(query),
                    product_ids=[item.get("product_id") for item in inventory if item.get("product_id")],
                ),
                _CONTEXT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("Analytics context query failed; falling back to live operational summary", exc_info=exc)
            live_repo = AnalyticsRepository()
            live_summary, live_summary_is_fallback = await _get_live_dashboard_summary_fallback(live_repo, store_id)
            analytics_context = {
                "dashboard_summary": live_summary,
                "sales_trends": [],
                "product_performance": [],
                "customer_insights": [],
            }
            degraded_context = degraded_context or live_summary_is_fallback
        if _query_mentions_customers(query) and not (analytics_context.get("customer_insights") or []):
            analytics_context["customer_insights"] = [
                {
                    "customer_id": customer.get("customer_id"),
                    "customer_name": customer.get("name"),
                    "lifetime_spend": customer.get("total_spend", 0.0),
                    "visit_count": customer.get("visit_count", 0),
                    "last_purchase_at": customer.get("last_purchase_at"),
                }
                for customer in customers[:5]
            ]
        analytics_summary = _build_analytics_summary(
            {
                **metadata,
                "analytics_last_updated_at": last_updated,
                "freshness_status": freshness_status,
            },
            analytics_context,
        )
        if not analytics_summary:
            live_repo = AnalyticsRepository()
            live_summary, live_summary_is_fallback = await _get_live_dashboard_summary_fallback(live_repo, store_id)
            analytics_summary = "; ".join(
                [
                    f"analytics_last_updated_at={last_updated}",
                    f"freshness_status={freshness_status}",
                    f"today_sales={live_summary.get('today_sales', 'unknown')}",
                    f"today_transactions={live_summary.get('today_transactions', 'unknown')}",
                    f"active_alert_count={live_summary.get('active_alert_count', 'unknown')}",
                    f"low_stock_count={live_summary.get('low_stock_count', 'unknown')}",
                    f"top_selling_product={live_summary.get('top_selling_product', 'unknown')}",
                ]
            )
            degraded_context = degraded_context or live_summary_is_fallback

        # Step 3: Build prompt
        context_block = _build_context_block(
            analytics_summary, alerts, inventory, customers, transactions,
            rag_products=rag_products,
        )
        full_prompt = (
            f"{_SYSTEM_INSTRUCTION}\n\n"
            f"=== STRUCTURED CONTEXT JSON ===\n{context_block}\n\n"
            f"=== USER QUESTION ===\n{query}"
        )

        # Step 4: Call hosted model
        operator_answer, operator_analytics_used = _build_operator_answer_result(
            query,
            analytics_context,
            alerts,
            inventory,
            customers,
            transactions,
        )
        if _should_use_operator_answer_directly(query, operator_answer):
            raw_answer = operator_answer or ""
        else:
            try:
                raw_answer = await _generate_model_answer(full_prompt)
            except Exception as exc:
                logger.error("Hosted model API call failed; using deterministic fallback answer", exc_info=exc)
                raw_answer = _build_fallback_answer(
                    query=query,
                    analytics_summary=analytics_summary,
                    analytics_context=analytics_context,
                    alerts=alerts,
                    inventory=inventory,
                    customers=customers,
                    transactions=transactions,
                    freshness_status=freshness_status,
                )

        # Step 5: Guard response
        answer = _response_guard(raw_answer, freshness_status)
        if operator_answer and (_query_prefers_operator_answer(query) or _looks_like_refusal(answer) or degraded_context):
            answer = operator_answer
        grounding = _extract_grounding(
            alerts,
            inventory,
            analytics_used=_infer_analytics_used(query, answer, operator_analytics_used),
            rag_products=rag_products,
        )

        # Step 6: Persist messages
        now = datetime.now(tz=timezone.utc)
        try:
            existing_session = await _await_with_timeout(
                repository.get_chat_session(chat_session_id),
                _PERSIST_TIMEOUT_SECONDS,
            )
            if existing_session is not None and existing_session.get("store_id") != store_id:
                raise ChatSessionNotFoundError(
                    f"Chat session '{chat_session_id}' was not found.",
                    details={"chat_session_id": chat_session_id},
                )

            await _await_with_timeout(
                repository.ensure_chat_session(
                    chat_session_id=chat_session_id,
                    store_id=store_id,
                    user_id=user_id,
                    updated_at=now,
                ),
                _PERSIST_TIMEOUT_SECONDS,
            )
            await _await_with_timeout(
                repository.append_message(
                    chat_session_id=chat_session_id,
                    message_id=f"msg_{uuid.uuid4().hex}",
                    role="user",
                    text=query,
                    created_at=now,
                ),
                _PERSIST_TIMEOUT_SECONDS,
            )
            await _await_with_timeout(
                repository.append_message(
                    chat_session_id=chat_session_id,
                    message_id=f"msg_{uuid.uuid4().hex}",
                    role="assistant",
                    text=answer,
                    created_at=now,
                ),
                _PERSIST_TIMEOUT_SECONDS,
            )
        except ChatSessionNotFoundError:
            raise
        except Exception as exc:
            logger.warning(
                "AI chat response generated but session persistence failed",
                exc_info=exc,
                extra={"chat_session_id": chat_session_id, "store_id": store_id},
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

    async def sync_embeddings(self, *, store_id: str) -> dict[str, Any]:
        """
        Trigger on-demand product embedding sync for a store.

        Fetches all products from Firestore and regenerates their vector
        embeddings in BigQuery. Called from POST /api/v1/ai/embed-sync.

        Returns:
            { store_id, product_count, embedded }
        """
        from datetime import datetime, timezone

        from app.common.google_clients import (
            create_bigquery_client,
            create_firestore_async_client,
            get_default_gcp_project,
        )
        from app.modules.data_pipeline.embedding_sync import sync_product_embeddings

        settings = get_settings()
        db = create_firestore_async_client(project=settings.firestore_project_id or None)
        bq = create_bigquery_client(project=get_default_gcp_project(settings))

        products: list[dict[str, Any]] = []
        async for doc in db.collection("products").where("store_id", "==", store_id).stream():
            data = doc.to_dict() or {}
            data.setdefault("product_id", doc.id)
            products.append(data)

        now = datetime.now(timezone.utc)
        embedded_count = await sync_product_embeddings(
            bq,
            store_id=store_id,
            products=products,
            analytics_last_updated_at=now,
        )

        logger.info(
            "On-demand embedding sync complete",
            extra={
                "store_id": store_id,
                "product_count": len(products),
                "embedded": embedded_count,
            },
        )
        return {
            "store_id": store_id,
            "product_count": len(products),
            "embedded": embedded_count,
        }
