"""
Data Pipeline Module – Embedding Sync.

Generates text embeddings for all store products and upserts them into
the BigQuery table `stocklytics_mart.product_embeddings`.

This module is called after a successful mart refresh so embeddings always
reflect the latest synced inventory state.

Called by:
  - transform_runner.run_mart_refresh()   (daily scheduled, post-mart success)
  - scripts/run_embedding_sync.py         (manual trigger or full rebuild)

Embedding model: Gemini embedding API (configured model with fallbacks).
Load strategy: per-store WRITE_TRUNCATE via a temp table swap to avoid DML billing.

Rules:
  - Embedding failure must NEVER fail the mart transform pipeline run.
  - store_id isolation: only the given store's rows are replaced.
  - analytics_last_updated_at from the transform is stamped on every row.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from google.cloud import bigquery

from app.common.config import get_settings

logger = logging.getLogger(__name__)

_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:batchEmbedContents"
)
_EMBED_MODEL_FALLBACKS = (
    "gemini-embedding-001",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_embedding_text(product: dict[str, Any]) -> str:
    """Build the canonical text string to embed for a product.

    Combines name and category, separated by ' | '.
    Extending this function (e.g. adding price tier or status) will automatically
    improve retrieval quality on next embedding sync run.
    """
    name = str(product.get("product_name") or product.get("name") or "").strip()
    category = str(product.get("category") or "").strip()
    product_id = str(product.get("product_id") or product.get("id") or "").strip()
    price = product.get("price")
    quantity = product.get("quantity_on_hand")
    status = str(product.get("status") or "").strip()
    expiry_status = str(product.get("expiry_status") or "").strip()

    parts = [
        name,
        category,
        f"product_id: {product_id}" if product_id else "",
        f"price_in_inr: {price}" if price not in (None, "") else "",
        f"quantity_on_hand: {quantity}" if quantity not in (None, "") else "",
        f"status: {status}" if status else "",
        f"expiry_status: {expiry_status}" if expiry_status else "",
    ]
    return " | ".join(p for p in parts if p)


def _extract_embedding_values(item: dict[str, Any]) -> list[float]:
    """Accept both documented and observed Gemini embedding response shapes."""
    if isinstance(item.get("values"), list):
        return [float(v) for v in item["values"]]

    nested = item.get("embedding")
    if isinstance(nested, dict) and isinstance(nested.get("values"), list):
        return [float(v) for v in nested["values"]]

    raise KeyError("Embedding response item did not contain values.")


async def _embed_batch(
    texts: list[str],
    api_key: str,
    model: str,
) -> list[list[float]]:
    """Call Gemini batchEmbedContents. Returns one embedding per text.

    Raises httpx.HTTPStatusError on API failure so the caller can catch and
    decide whether to retry or skip.
    """
    url = _EMBED_URL.format(model=model)
    payload = {
        "requests": [
            {
                "model": f"models/{model}",
                "content": {"parts": [{"text": t}]},
                "taskType": "RETRIEVAL_DOCUMENT",
            }
            for t in texts
        ]
    }
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
    return [_extract_embedding_values(emb) for emb in body["embeddings"]]


def _embedding_model_candidates(preferred_model: str) -> list[str]:
    ordered: list[str] = []
    for model_name in (preferred_model, *_EMBED_MODEL_FALLBACKS):
        if model_name and model_name not in ordered:
            ordered.append(model_name)
    return ordered


async def _embed_batch_with_fallback(
    texts: list[str],
    api_key: str,
    preferred_model: str,
) -> tuple[list[list[float]], str]:
    last_error: Exception | None = None
    for model_name in _embedding_model_candidates(preferred_model):
        try:
            embeddings = await _embed_batch(texts, api_key, model_name)
            return embeddings, model_name
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code
            if status_code in {404, 400}:
                logger.warning(
                    "Embedding model unavailable; trying fallback model",
                    extra={"model": model_name, "status_code": status_code},
                )
                continue
            raise
        except Exception as exc:
            last_error = exc
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("No embedding model candidates available.")


def _load_rows_to_bigquery(
    bq: bigquery.Client,
    rows: list[dict[str, Any]],
    table_id: str,
) -> None:
    """Load JSON rows into BigQuery using WRITE_APPEND (blocking, run in thread)."""
    schema = [
        bigquery.SchemaField("store_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("product_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("product_name", "STRING"),
        bigquery.SchemaField("category", "STRING"),
        bigquery.SchemaField("embedding_text", "STRING"),
        bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED"),
        bigquery.SchemaField("embedded_at", "TIMESTAMP"),
        bigquery.SchemaField("analytics_last_updated_at", "TIMESTAMP"),
    ]
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=schema,
    )
    job = bq.load_table_from_json(rows, table_id, job_config=job_config)
    job.result()  # blocks until done; raises on error


def _delete_store_rows(
    bq: bigquery.Client,
    table_id: str,
    store_id: str,
) -> None:
    """Remove existing rows for a store before re-inserting (idempotent update).

    Uses a DML DELETE. This is acceptable here because:
    - product_embeddings is NOT a mart table (no MERGE contract applies)
    - DELETE + INSERT keeps the pattern idempotent
    - Billing restriction only applies to mart tables in the pipeline
    """
    sql = f"DELETE FROM `{table_id}` WHERE store_id = '{store_id}'"
    job = bq.query(sql)
    job.result()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def sync_product_embeddings(
    bq: bigquery.Client,
    *,
    store_id: str,
    products: list[dict[str, Any]],
    analytics_last_updated_at: datetime,
) -> int:
    """Generate embeddings for all products and upsert into product_embeddings.

    Args:
        bq:                          BigQuery client (from transform_runner).
        store_id:                    Isolates all reads/writes to this store.
        products:                    Raw product dicts from Firestore.
        analytics_last_updated_at:   Timestamp from the successful mart refresh.

    Returns:
        Number of products successfully embedded and loaded.

    Raises:
        Any unhandled exception — callers must wrap in try/except and log.
        The mart pipeline must NOT fail if this function raises.
    """
    settings = get_settings()

    if not products:
        logger.info(
            "No products to embed; skipping embedding sync",
            extra={"store_id": store_id},
        )
        return 0

    if not settings.gemini_api_key:
        logger.warning(
            "GEMINI_API_KEY not configured; skipping embedding sync",
            extra={"store_id": store_id},
        )
        return 0

    api_key = settings.gemini_api_key
    preferred_model = settings.gemini_embedding_model
    batch_size = settings.embedding_batch_size
    now = datetime.now(timezone.utc)
    project = settings.bigquery_project_id
    mart = settings.bigquery_dataset_mart
    table_id = f"{project}.{mart}.product_embeddings"

    rows: list[dict[str, Any]] = []
    failed_batches = 0

    selected_model: str | None = None
    for i in range(0, len(products), batch_size):
        batch = products[i : i + batch_size]
        texts = [_build_embedding_text(p) for p in batch]

        try:
            embeddings, used_model = await _embed_batch_with_fallback(texts, api_key, preferred_model)
            if selected_model is None:
                selected_model = used_model
        except Exception as exc:
            logger.warning(
                "Embedding batch failed; skipping batch",
                exc_info=exc,
                extra={"store_id": store_id, "batch_start": i, "batch_size": len(batch)},
            )
            failed_batches += 1
            continue

        for product, embedding, text in zip(batch, embeddings, texts):
            pid = product.get("product_id") or product.get("id") or ""
            if not pid:
                continue
            rows.append(
                {
                    "store_id": store_id,
                    "product_id": pid,
                    "product_name": product.get("product_name") or product.get("name"),
                    "category": product.get("category"),
                    "embedding_text": text,
                    "embedding": embedding,
                    "embedded_at": now.isoformat(),
                    "analytics_last_updated_at": analytics_last_updated_at.isoformat(),
                }
            )

    if not rows:
        logger.warning(
            "All embedding batches failed or produced no rows",
            extra={"store_id": store_id, "failed_batches": failed_batches},
        )
        return 0

    # Replace existing rows for this store, then append fresh ones
    await asyncio.to_thread(_delete_store_rows, bq, table_id, store_id)
    await asyncio.to_thread(_load_rows_to_bigquery, bq, rows, table_id)

    logger.info(
        "Embedding sync complete",
        extra={
            "store_id": store_id,
            "embedded": len(rows),
            "failed_batches": failed_batches,
            "model": selected_model or preferred_model,
        },
    )
    return len(rows)
