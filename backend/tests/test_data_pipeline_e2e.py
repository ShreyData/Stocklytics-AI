import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import sys

# Mock GCP libraries before importing app to prevent auth hangs
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.bigquery'] = MagicMock()

from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

AUTH_HEADER = {"Authorization": "Bearer dev-token"}
BAD_AUTH_HEADER = {"Authorization": "Bearer bad-token"}

@pytest.fixture
def mock_repository_trigger():
    with patch("app.modules.data_pipeline.repository.get_active_run_for_store", new_callable=AsyncMock) as m_active:
        m_active.return_value = None
        with patch("app.modules.data_pipeline.repository.create_pipeline_run", new_callable=AsyncMock) as m_create:
            m_create.return_value = "run_trigger_123"
            with patch("app.modules.data_pipeline.checkpoint_manager.get_checkpoint_window", new_callable=AsyncMock) as m_window:
                m_window.return_value = (datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 2, tzinfo=timezone.utc))
                yield m_active, m_create, m_window

class TestDataPipelineRouter:

    def test_sync_trigger_unauthorized(self):
        response = client.post("/api/v1/pipeline/runs/sync")
        assert response.status_code == 401

    def test_sync_trigger_success(self, mock_repository_trigger):
        # Trigger should return 202 ACCEPTED with QUEUED status
        # Since it creates an asyncio.create_task, we mock the background execution dependencies
        with patch("app.modules.data_pipeline.service.sync_runner.run_incremental_sync", new_callable=AsyncMock) as m_sync:
            response = client.post("/api/v1/pipeline/runs/sync", headers=AUTH_HEADER)
            assert response.status_code == 202
            data = response.json()
            assert "pipeline_run" in data
            assert data["pipeline_run"]["pipeline_run_id"] == "run_trigger_123"
            assert data["pipeline_run"]["status"] == "QUEUED"

    def test_sync_trigger_already_running(self):
        with patch("app.modules.data_pipeline.repository.get_active_run_for_store", new_callable=AsyncMock) as m_active:
            m_active.return_value = {"pipeline_run_id": "run_active_123"}
            response = client.post("/api/v1/pipeline/runs/sync", headers=AUTH_HEADER)
            assert response.status_code == 409
            data = response.json()
            assert data["error"]["code"] == "PIPELINE_ALREADY_RUNNING"
            assert data["error"]["details"]["active_pipeline_run_id"] == "run_active_123"

    def test_get_run_status_success(self):
        with patch("app.modules.data_pipeline.repository.get_pipeline_run", new_callable=AsyncMock) as m_get:
            # We mock the return dict as it would be returned from Firestore
            m_get.return_value = {
                "pipeline_run_id": "run_123",
                "store_id": "dev-store",
                "status": "SUCCEEDED",
                "run_type": "INCREMENTAL_SYNC",
                "records_read": 100,
                "records_written": 100,
                "error_message": None,
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            response = client.get("/api/v1/pipeline/runs/run_123", headers=AUTH_HEADER)
            assert response.status_code == 200
            data = response.json()
            assert data["pipeline_run"]["pipeline_run_id"] == "run_123"
            assert data["pipeline_run"]["status"] == "SUCCEEDED"

    def test_get_run_status_not_found(self):
        with patch("app.modules.data_pipeline.repository.get_pipeline_run", new_callable=AsyncMock) as m_get:
            m_get.return_value = None
            response = client.get("/api/v1/pipeline/runs/run_123", headers=AUTH_HEADER)
            assert response.status_code == 404
            data = response.json()
            assert data["error"]["code"] == "PIPELINE_RUN_NOT_FOUND"

    def test_get_run_status_wrong_store(self):
        with patch("app.modules.data_pipeline.repository.get_pipeline_run", new_callable=AsyncMock) as m_get:
            m_get.return_value = {
                "pipeline_run_id": "run_123",
                "store_id": "other-store", # current dev token is "dev-store"
                "status": "SUCCEEDED",
            }
            response = client.get("/api/v1/pipeline/runs/run_123", headers=AUTH_HEADER)
            assert response.status_code == 404
            data = response.json()
            assert data["error"]["code"] == "PIPELINE_RUN_NOT_FOUND"
