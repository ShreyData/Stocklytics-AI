"""
AI Module – Repository layer.

Isolates all Firestore read/write operations for the AI chat module.
The service layer calls only these functions; routes never touch Firestore directly.

Collections:
    ai_chat_sessions        – parent document per chat session
    ai_chat_sessions/{id}/messages – ordered message subcollection
    analytics_metadata      – freshness metadata (read-only by AI module)
    alerts                  – active alerts snapshot (read-only by AI module)
    products                – inventory snapshot (read-only by AI module)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from google.cloud import bigquery
from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

from app.common.config import get_settings
from app.common.google_clients import (
    create_bigquery_client,
    create_firestore_async_client,
    get_default_gcp_project,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Firestore client (lazy singleton)
# ---------------------------------------------------------------------------

_db: Optional[firestore.AsyncClient] = None
_bq: Optional[bigquery.Client] = None


def _get_db() -> firestore.AsyncClient:
    """Return a cached Firestore async client, initialising on first call."""
    global _db
    if _db is None:
        settings = get_settings()
        project = settings.firestore_project_id or None
        _db = create_firestore_async_client(project=project)
    return _db


def _get_bq() -> bigquery.Client:
    """Return a cached BigQuery client, initialising on first call."""
    global _bq
    if _bq is None:
        settings = get_settings()
        project = get_default_gcp_project(settings)
        _bq = create_bigquery_client(project=project)
    return _bq


# ---------------------------------------------------------------------------
# Collection constants
# ---------------------------------------------------------------------------

SESSIONS_COLLECTION = "ai_chat_sessions"
MESSAGES_SUBCOLLECTION = "messages"
ANALYTICS_METADATA_COLLECTION = "analytics_metadata"
ALERTS_COLLECTION = "alerts"
PRODUCTS_COLLECTION = "products"


# ---------------------------------------------------------------------------
# Analytics metadata (freshness)
# ---------------------------------------------------------------------------

async def get_analytics_metadata(store_id: str) -> Optional[dict[str, Any]]:
    """
    Read analytics_metadata for the given store.
    Returns None if no metadata document exists yet.
    """
    db = _get_db()
    metadata_id = f"{store_id}_dashboard"
    doc: DocumentSnapshot = await db.collection(ANALYTICS_METADATA_COLLECTION).document(metadata_id).get()
    if not doc.exists:
        return None
    data: dict[str, Any] = doc.to_dict() or {}
    return _normalise_timestamps(data)


# ---------------------------------------------------------------------------
# Context fetchers (read-only consumers from other modules' collections)
# ---------------------------------------------------------------------------

async def get_active_alerts_snapshot(store_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Return up to `limit` ACTIVE alerts for the store to provide context to Gemini.
    Reads directly from the alerts collection (owned by Alerts module).
    """
    db = _get_db()
    query = (
        db.collection(ALERTS_COLLECTION)
        .where("store_id", "==", store_id)
        .where("status", "==", "ACTIVE")
        .limit(limit)
    )
    results: list[dict[str, Any]] = []
    async for doc in query.stream():
        data: dict[str, Any] = doc.to_dict() or {}
        if "alert_id" not in data:
            data["alert_id"] = doc.id
        results.append(data)
    return results


async def get_relevant_alerts_snapshot(store_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Return alerts relevant for AI grounding.

    Active alerts are always preferred. If there is room remaining, recent
    acknowledged alerts are also included so the AI can still reference issues
    that may matter to the current question.
    """
    active_alerts = await get_active_alerts_snapshot(store_id=store_id, limit=limit)
    if len(active_alerts) >= limit:
        return active_alerts

    db = _get_db()
    acknowledged_query = (
        db.collection(ALERTS_COLLECTION)
        .where("store_id", "==", store_id)
        .where("status", "==", "ACKNOWLEDGED")
        .limit(limit - len(active_alerts))
    )
    acknowledged_alerts: list[dict[str, Any]] = []
    async for doc in acknowledged_query.stream():
        data: dict[str, Any] = doc.to_dict() or {}
        if "alert_id" not in data:
            data["alert_id"] = doc.id
        acknowledged_alerts.append(data)

    return active_alerts + acknowledged_alerts


async def get_inventory_snapshot(
    store_id: str,
    limit: int = 10,
    product_ids: Optional[list[str]] = None,
    query_text: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Return up to `limit` products for the store to ground the AI in current inventory reality.
    Reads directly from the products collection (owned by Inventory module).
    """
    db = _get_db()
    fetch_limit = max(limit * 5, 25)
    query = (
        db.collection(PRODUCTS_COLLECTION)
        .where("store_id", "==", store_id)
        .limit(fetch_limit)
    )
    results: list[dict[str, Any]] = []
    async for doc in query.stream():
        data: dict[str, Any] = doc.to_dict() or {}
        if "product_id" not in data:
            data["product_id"] = doc.id
        results.append(data)

    requested_ids = set(product_ids or [])
    query_tokens = {
        token
        for token in _normalise_query_tokens(query_text or "")
        if len(token) >= 3
    }

    focused: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for item in results:
        product_id = str(item.get("product_id", ""))
        product_name = str(item.get("name", "")).lower()
        if product_id in requested_ids or any(token in product_name for token in query_tokens):
            focused.append(item)
        else:
            fallback.append(item)

    ordered = focused + fallback
    return ordered[:limit]


# ---------------------------------------------------------------------------
# BigQuery mart readers (analytics context for AI)
# ---------------------------------------------------------------------------

async def get_analytics_context(
    store_id: str,
    include_customer_insights: bool = False,
    product_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Fetch a compact analytics context from BigQuery mart tables.

    The AI service uses this to build the strict `analytics_summary` text field
    required by the AI system design.
    """
    settings = get_settings()
    project = settings.bigquery_project_id
    mart = settings.bigquery_dataset_mart
    if not project:
        raise RuntimeError("BIGQUERY_PROJECT_ID is not configured.")
    bq = _get_bq()

    dashboard_sql = f"""
        SELECT
            snapshot_date,
            today_sales,
            today_transactions,
            active_alert_count,
            low_stock_count,
            top_selling_product,
            analytics_last_updated_at
        FROM `{project}.{mart}.dashboard_summary`
        WHERE store_id = @store_id
        ORDER BY snapshot_date DESC
        LIMIT 1
    """

    sales_sql = f"""
        SELECT
            sales_date,
            total_sales,
            transaction_count,
            average_basket_value
        FROM `{project}.{mart}.sales_daily`
        WHERE store_id = @store_id
        ORDER BY sales_date DESC
        LIMIT @limit
    """

    if product_ids:
        product_sql = f"""
            WITH ranked_products AS (
                SELECT
                    product_id,
                    product_name,
                    quantity_sold,
                    revenue,
                    sales_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY product_id
                        ORDER BY sales_date DESC
                    ) AS row_num
                FROM `{project}.{mart}.product_sales_daily`
                WHERE store_id = @store_id
                  AND product_id IN UNNEST(@product_ids)
            )
            SELECT product_id, product_name, quantity_sold, revenue, sales_date
            FROM ranked_products
            WHERE row_num = 1
            ORDER BY revenue DESC, quantity_sold DESC
            LIMIT @limit
        """
        product_parameters = [
            bigquery.ScalarQueryParameter("store_id", "STRING", store_id),
            bigquery.ArrayQueryParameter("product_ids", "STRING", product_ids),
            bigquery.ScalarQueryParameter("limit", "INT64", 3),
        ]
    else:
        product_sql = f"""
            WITH ranked_products AS (
                SELECT
                    product_id,
                    product_name,
                    quantity_sold,
                    revenue,
                    sales_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY product_id
                        ORDER BY sales_date DESC
                    ) AS row_num
                FROM `{project}.{mart}.product_sales_daily`
                WHERE store_id = @store_id
            )
            SELECT product_id, product_name, quantity_sold, revenue, sales_date
            FROM ranked_products
            WHERE row_num = 1
            ORDER BY revenue DESC, quantity_sold DESC
            LIMIT @limit
        """
        product_parameters = [
            bigquery.ScalarQueryParameter("store_id", "STRING", store_id),
            bigquery.ScalarQueryParameter("limit", "INT64", 3),
        ]

    customer_sql = f"""
        SELECT
            customer_id,
            customer_name,
            lifetime_spend,
            visit_count,
            last_purchase_at
        FROM `{project}.{mart}.customer_summary`
        WHERE store_id = @store_id
        ORDER BY lifetime_spend DESC, visit_count DESC
        LIMIT @limit
    """

    dashboard_rows = await _run_bigquery(
        bq,
        dashboard_sql,
        [
            bigquery.ScalarQueryParameter("store_id", "STRING", store_id),
        ],
    )
    sales_rows = await _run_bigquery(
        bq,
        sales_sql,
        [
            bigquery.ScalarQueryParameter("store_id", "STRING", store_id),
            bigquery.ScalarQueryParameter("limit", "INT64", 7),
        ],
    )
    product_rows = await _run_bigquery(bq, product_sql, product_parameters)

    customer_rows: list[dict[str, Any]] = []
    if include_customer_insights:
        customer_rows = await _run_bigquery(
            bq,
            customer_sql,
            [
                bigquery.ScalarQueryParameter("store_id", "STRING", store_id),
                bigquery.ScalarQueryParameter("limit", "INT64", 3),
            ],
        )

    return {
        "dashboard_summary": dashboard_rows[0] if dashboard_rows else None,
        "sales_trends": sales_rows,
        "product_performance": product_rows,
        "customer_insights": customer_rows,
    }


# ---------------------------------------------------------------------------
# Chat session persistence
# ---------------------------------------------------------------------------

async def get_chat_session(chat_session_id: str) -> Optional[dict[str, Any]]:
    """Fetch the session document. Returns None if the session does not exist."""
    db = _get_db()
    doc: DocumentSnapshot = await db.collection(SESSIONS_COLLECTION).document(chat_session_id).get()
    if not doc.exists:
        return None
    return _normalise_timestamps(doc.to_dict() or {})


async def ensure_chat_session(
    chat_session_id: str,
    store_id: str,
    user_id: str,
    updated_at: datetime,
) -> None:
    """
    Create the session parent document if it does not already exist.
    Uses set with merge=True so replays are safe.
    """
    db = _get_db()
    doc_ref = db.collection(SESSIONS_COLLECTION).document(chat_session_id)
    existing_doc = await doc_ref.get()
    if existing_doc.exists:
        await doc_ref.set(
            {
                "last_query_at": updated_at,
                "store_id": store_id,
                "user_id": user_id,
            },
            merge=True,
        )
        return

    await doc_ref.set(
        {
            "chat_session_id": chat_session_id,
            "store_id": store_id,
            "user_id": user_id,
            "created_at": updated_at,
            "last_query_at": updated_at,
        }
    )


async def append_message(
    chat_session_id: str,
    message_id: str,
    role: str,
    text: str,
    created_at: datetime,
) -> None:
    """
    Append a single message document to the session's messages subcollection.

    Args:
        chat_session_id: Parent session identifier.
        message_id:      Unique ID for this message document.
        role:            'user' or 'assistant'.
        text:            The message content.
        created_at:      UTC datetime of the message.
    """
    db = _get_db()
    msg_ref = (
        db.collection(SESSIONS_COLLECTION)
        .document(chat_session_id)
        .collection(MESSAGES_SUBCOLLECTION)
        .document(message_id)
    )
    await msg_ref.set({
        "role": role,
        "text": text,
        "created_at": created_at,
    })
    logger.info(
        "Chat message appended",
        extra={"chat_session_id": chat_session_id, "role": role},
    )


async def list_messages(chat_session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """
    Return the most recent messages for a session, ordered by creation time ascending.

    Args:
        chat_session_id: The session to fetch messages from.
        limit:           Maximum number of messages to return.
    """
    db = _get_db()
    query = (
        db.collection(SESSIONS_COLLECTION)
        .document(chat_session_id)
        .collection(MESSAGES_SUBCOLLECTION)
        .order_by("created_at")
        .limit(limit)
    )
    results: list[dict[str, Any]] = []
    async for doc in query.stream():
        data: dict[str, Any] = doc.to_dict() or {}
        results.append(_normalise_timestamps(data))
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_timestamps(data: dict[str, Any]) -> dict[str, Any]:
    """Convert Firestore DatetimeWithNanoseconds values to ISO-8601 UTC strings."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


async def _run_bigquery(
    bq: bigquery.Client,
    sql: str,
    params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter],
) -> list[dict[str, Any]]:
    """Execute a BigQuery query off the event loop and normalise rows."""

    def _query() -> list[dict[str, Any]]:
        config = bigquery.QueryJobConfig(query_parameters=params)
        job = bq.query(sql, job_config=config)
        rows = job.result()
        return [_normalise_bigquery_row(dict(row.items())) for row in rows]

    return await asyncio.to_thread(_query)


def _normalise_bigquery_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert BigQuery row values into API-safe Python primitives."""
    result: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            result[key] = value.isoformat()
        elif isinstance(value, date):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = float(value)
        else:
            result[key] = value
    return result


def _normalise_query_tokens(query_text: str) -> set[str]:
    return {
        token.strip(".,!?-_/").lower()
        for token in query_text.split()
        if token.strip(".,!?-_/")
    }
