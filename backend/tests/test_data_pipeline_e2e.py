from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.auth import AuthenticatedUser, require_admin, require_auth
from app.common.exceptions import register_exception_handlers
from app.common.middleware import RequestIdMiddleware
from app.modules.data_pipeline.router import router as pipeline_router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(pipeline_router, prefix="/api/v1/pipeline")
    return app


@pytest.fixture
def client() -> TestClient:
    app = _build_app()

    async def _admin_user() -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id="dev_user_001",
            role="admin",
            store_id="store_001",
            email="dev@stocklytics.local",
        )

    app.dependency_overrides[require_auth] = _admin_user
    app.dependency_overrides[require_admin] = _admin_user
    return TestClient(app, raise_server_exceptions=False)


class TestDataPipelineRouter:
    def test_sync_trigger_success(self, client: TestClient) -> None:
        with patch(
            "app.modules.data_pipeline.service._get_firestore",
            return_value=AsyncMock(),
        ), patch(
            "app.modules.data_pipeline.service._get_bigquery",
            return_value=MagicMock(),
        ), patch(
            "app.modules.data_pipeline.repository.get_active_run_for_store",
            new_callable=AsyncMock,
        ) as mock_active, patch(
            "app.modules.data_pipeline.checkpoint_manager.get_checkpoint_window",
            new_callable=AsyncMock,
        ) as mock_window, patch(
            "app.modules.data_pipeline.repository.create_pipeline_run",
            new_callable=AsyncMock,
        ) as mock_create, patch(
            "app.modules.data_pipeline.service.sync_runner.run_incremental_sync",
            new_callable=AsyncMock,
        ):
            mock_active.return_value = None
            mock_window.return_value = (
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
            )
            mock_create.return_value = "run_trigger_123"

            response = client.post(
                "/api/v1/pipeline/runs/sync",
                json={"store_id": "store_001", "trigger_mode": "manual"},
            )

            assert response.status_code == 202
            data = response.json()
            assert data["pipeline_run_id"] == "run_trigger_123"
            assert data["status"] == "QUEUED"

    def test_sync_trigger_already_running(self, client: TestClient) -> None:
        with patch(
            "app.modules.data_pipeline.service._get_firestore",
            return_value=AsyncMock(),
        ), patch(
            "app.modules.data_pipeline.service._get_bigquery",
            return_value=MagicMock(),
        ), patch(
            "app.modules.data_pipeline.repository.get_active_run_for_store",
            new_callable=AsyncMock,
        ) as mock_active:
            mock_active.return_value = {"pipeline_run_id": "run_active_123"}

            response = client.post(
                "/api/v1/pipeline/runs/sync",
                json={"store_id": "store_001", "trigger_mode": "manual"},
            )

            assert response.status_code == 409
            data = response.json()
            assert data["error"]["code"] == "PIPELINE_ALREADY_RUNNING"
            assert data["error"]["details"]["active_pipeline_run_id"] == "run_active_123"

    def test_sync_trigger_rejects_store_scope_mismatch(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/pipeline/runs/sync",
            json={"store_id": "store_999", "trigger_mode": "manual"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "INVALID_REQUEST"
        assert data["error"]["details"]["request_store_id"] == "store_999"
        assert data["error"]["details"]["auth_store_id"] == "store_001"

    def test_get_run_status_success(self, client: TestClient) -> None:
        with patch(
            "app.modules.data_pipeline.service._get_firestore",
            return_value=AsyncMock(),
        ), patch(
            "app.modules.data_pipeline.repository.get_pipeline_run",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "pipeline_run_id": "run_123",
                "store_id": "store_001",
                "status": "SUCCEEDED",
                "attempt_count": 1,
                "started_at": datetime.now(tz=timezone.utc),
                "finished_at": None,
                "failure_stage": None,
                "error_message": None,
            }

            response = client.get("/api/v1/pipeline/runs/run_123")

            assert response.status_code == 200
            data = response.json()
            assert data["pipeline_run"]["pipeline_run_id"] == "run_123"
            assert data["pipeline_run"]["status"] == "SUCCEEDED"

    def test_get_run_status_wrong_store(self, client: TestClient) -> None:
        with patch(
            "app.modules.data_pipeline.service._get_firestore",
            return_value=AsyncMock(),
        ), patch(
            "app.modules.data_pipeline.repository.get_pipeline_run",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "pipeline_run_id": "run_123",
                "store_id": "store_999",
                "status": "SUCCEEDED",
            }

            response = client.get("/api/v1/pipeline/runs/run_123")

            assert response.status_code == 404
            data = response.json()
            assert data["error"]["code"] == "PIPELINE_RUN_NOT_FOUND"

    def test_get_run_status_requires_admin_or_manager(self, client: TestClient) -> None:
        app = client.app

        async def _staff_user() -> AuthenticatedUser:
            return AuthenticatedUser(
                user_id="staff_001",
                role="staff",
                store_id="store_001",
                email="staff@stocklytics.local",
            )

        app.dependency_overrides[require_auth] = _staff_user

        response = client.get("/api/v1/pipeline/runs/run_123")

        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "FORBIDDEN"
