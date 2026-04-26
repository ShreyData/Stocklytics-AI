"""
Shared Google Cloud client helpers.

These helpers let local/dev environments authenticate Firestore and BigQuery
using the same service-account values already provided for Firebase Admin.
"""

from __future__ import annotations

from functools import lru_cache

from google.cloud import bigquery, firestore
from google.oauth2 import service_account

from app.common.config import Settings, get_settings


def get_default_gcp_project(settings: Settings | None = None) -> str | None:
    current = settings or get_settings()
    return (
        current.bigquery_project_id
        or current.firestore_project_id
        or current.firebase_project_id
        or None
    )


@lru_cache(maxsize=1)
def get_service_account_credentials():
    settings = get_settings()
    if not (
        settings.firebase_project_id
        and settings.firebase_client_email
        and settings.firebase_private_key
    ):
        return None

    return service_account.Credentials.from_service_account_info(
        {
            "type": "service_account",
            "project_id": settings.firebase_project_id,
            "client_email": settings.firebase_client_email,
            "private_key": settings.firebase_private_key.replace("\\n", "\n"),
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


def create_firestore_async_client(project: str | None = None) -> firestore.AsyncClient:
    settings = get_settings()
    return firestore.AsyncClient(
        project=project or get_default_gcp_project(settings),
        credentials=get_service_account_credentials(),
    )


def create_firestore_client(project: str | None = None) -> firestore.Client:
    settings = get_settings()
    return firestore.Client(
        project=project or get_default_gcp_project(settings),
        credentials=get_service_account_credentials(),
    )


def create_bigquery_client(project: str | None = None) -> bigquery.Client:
    settings = get_settings()
    return bigquery.Client(
        project=project or get_default_gcp_project(settings),
        credentials=get_service_account_credentials(),
    )
