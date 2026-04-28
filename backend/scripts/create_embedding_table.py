#!/usr/bin/env python3
"""
One-time setup: create the product_embeddings table in BigQuery.

Run ONCE before the first embedding sync. Idempotent (IF NOT EXISTS).

Usage:
    python -m scripts.create_embedding_table
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv(".env")

from app.common.config import get_settings
from app.common.google_clients import create_bigquery_client, get_default_gcp_project

DDL = """
CREATE TABLE IF NOT EXISTS `{project}.{mart}.product_embeddings` (
    store_id                  STRING    NOT NULL,
    product_id                STRING    NOT NULL,
    product_name              STRING,
    category                  STRING,
    embedding_text            STRING,
    embedding                 ARRAY<FLOAT64>,
    embedded_at               TIMESTAMP,
    analytics_last_updated_at TIMESTAMP
)
OPTIONS (
    description = 'Product text embeddings for RAG vector search. One row per product per store.'
);
"""


def main() -> None:
    settings = get_settings()
    project = settings.bigquery_project_id
    mart = settings.bigquery_dataset_mart
    if not project or not mart:
        raise RuntimeError("BIGQUERY_PROJECT_ID and BIGQUERY_DATASET_MART must be set in .env")

    bq = create_bigquery_client(project=get_default_gcp_project(settings))
    sql = DDL.format(project=project, mart=mart)
    print(f"Creating table: {project}.{mart}.product_embeddings")
    job = bq.query(sql)
    job.result()
    print("Done — table created (or already exists).")


if __name__ == "__main__":
    main()
