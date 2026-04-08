"""
Application configuration loaded from environment variables.
Central place for all config values. Import this module wherever settings are needed.
"""

import os
from functools import lru_cache


class Settings:
    """Holds all application configuration values."""

    app_env: str = os.getenv("APP_ENV", "local")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    # Firebase / Auth
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID", "")
    firebase_client_email: str = os.getenv("FIREBASE_CLIENT_EMAIL", "")
    firebase_private_key: str = os.getenv("FIREBASE_PRIVATE_KEY", "")

    # Firestore
    firestore_project_id: str = os.getenv("FIRESTORE_PROJECT_ID", "")

    # BigQuery
    bigquery_project_id: str = os.getenv("BIGQUERY_PROJECT_ID", "")
    bigquery_dataset_raw: str = os.getenv("BIGQUERY_DATASET_RAW", "retailmind_raw")
    bigquery_dataset_mart: str = os.getenv("BIGQUERY_DATASET_MART", "retailmind_mart")

    # Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of Settings."""
    return Settings()
