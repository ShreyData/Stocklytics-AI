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

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

from app.common.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Firestore client (lazy singleton)
# ---------------------------------------------------------------------------

_db: Optional[firestore.AsyncClient] = None


def _get_db() -> firestore.AsyncClient:
    """Return a cached Firestore async client, initialising on first call."""
    global _db
    if _db is None:
        settings = get_settings()
        project = settings.firestore_project_id or None
        _db = firestore.AsyncClient(project=project)
    return _db


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
    doc: DocumentSnapshot = await db.collection(ANALYTICS_METADATA_COLLECTION).document(store_id).get()
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


async def get_inventory_snapshot(store_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Return up to `limit` products for the store to ground the AI in current inventory reality.
    Reads directly from the products collection (owned by Inventory module).
    """
    db = _get_db()
    query = (
        db.collection(PRODUCTS_COLLECTION)
        .where("store_id", "==", store_id)
        .limit(limit)
    )
    results: list[dict[str, Any]] = []
    async for doc in query.stream():
        data: dict[str, Any] = doc.to_dict() or {}
        if "product_id" not in data:
            data["product_id"] = doc.id
        results.append(data)
    return results


# ---------------------------------------------------------------------------
# Chat session persistence
# ---------------------------------------------------------------------------

async def get_chat_session(chat_session_id: str) -> Optional[dict[str, Any]]:
    """Fetch the session document. Returns None if the session does not exist."""
    db = _get_db()
    doc: DocumentSnapshot = await db.collection(SESSIONS_COLLECTION).document(chat_session_id).get()
    if not doc.exists:
        return None
    return doc.to_dict() or {}


async def ensure_chat_session(chat_session_id: str, store_id: str) -> None:
    """
    Create the session parent document if it does not already exist.
    Uses set with merge=True so replays are safe.
    """
    db = _get_db()
    doc_ref = db.collection(SESSIONS_COLLECTION).document(chat_session_id)
    await doc_ref.set({"store_id": store_id, "chat_session_id": chat_session_id}, merge=True)


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
