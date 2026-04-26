"""
Test suite for API foundation – platform endpoints and core middleware.

Coverage per coding_instructions.txt testing expectations:
    - Happy path for /health, /ready, and /me
    - Validation / auth failure paths
    - Error response format matches api_contracts.md shared error model
    - request_id is present on every response

Run with: pytest backend/tests/ -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUTH_HEADER = {"Authorization": "Bearer dev-token"}
BAD_AUTH_HEADER = {"Authorization": "Bearer bad-token"}


def assert_error_shape(body: dict) -> None:
    """Assert the shared error response model is present."""
    assert "request_id" in body, "Missing request_id"
    assert "error" in body, "Missing error object"
    assert "code" in body["error"], "Missing error.code"
    assert "message" in body["error"], "Missing error.message"
    assert "details" in body["error"], "Missing error.details"


# ---------------------------------------------------------------------------
# GET /api/v1/health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self):
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self):
        body = client.get("/api/v1/health").json()
        assert body == {"status": "ok"}

    def test_health_requires_no_auth(self):
        """Health check must work without any Auth header."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_response_includes_x_request_id_header(self):
        response = client.get("/api/v1/health")
        assert "x-request-id" in response.headers


# ---------------------------------------------------------------------------
# GET /api/v1/ready
# ---------------------------------------------------------------------------

class TestReadyEndpoint:
    def test_ready_returns_200(self):
        response = client.get("/api/v1/ready")
        assert response.status_code == 200

    def test_ready_body_shape(self):
        body = client.get("/api/v1/ready").json()
        assert body["status"] == "ready"
        deps = body["dependencies"]
        assert "firestore" in deps
        assert "bigquery" in deps
        assert "gemini" in deps

    def test_ready_requires_no_auth(self):
        response = client.get("/api/v1/ready")
        assert response.status_code == 200

    def test_ready_response_includes_x_request_id_header(self):
        response = client.get("/api/v1/ready")
        assert "x-request-id" in response.headers

    def test_ready_returns_shared_error_shape_when_dependency_not_ready(self):
        with patch(
            "app.api.platform._probe_firestore",
            new_callable=AsyncMock,
            return_value="error",
        ):
            response = client.get("/api/v1/ready")

        assert response.status_code == 503
        body = response.json()
        assert_error_shape(body)
        assert body["error"]["code"] == "DEPENDENCIES_NOT_READY"
        assert body["error"]["details"]["dependencies"]["firestore"] == "error"


# ---------------------------------------------------------------------------
# GET /api/v1/me
# ---------------------------------------------------------------------------

class TestMeEndpoint:
    def test_me_returns_401_without_token(self):
        response = client.get("/api/v1/me")
        assert response.status_code == 401
        assert_error_shape(response.json())

    def test_me_returns_401_with_invalid_token(self):
        response = client.get("/api/v1/me", headers=BAD_AUTH_HEADER)
        assert response.status_code == 401
        body = response.json()
        assert_error_shape(body)
        assert body["error"]["code"] == "UNAUTHORIZED"

    def test_me_returns_200_with_dev_token(self):
        response = client.get("/api/v1/me", headers=AUTH_HEADER)
        assert response.status_code == 200

    def test_me_body_shape_with_dev_token(self):
        body = client.get("/api/v1/me", headers=AUTH_HEADER).json()
        assert "request_id" in body
        assert "user" in body
        user = body["user"]
        assert "user_id" in user
        assert "role" in user
        assert "store_id" in user

    def test_me_response_includes_x_request_id_header(self):
        response = client.get("/api/v1/me", headers=AUTH_HEADER)
        assert "x-request-id" in response.headers

    def test_me_request_id_matches_body_and_header(self):
        """The X-Request-ID header and body request_id must be the same value."""
        response = client.get("/api/v1/me", headers=AUTH_HEADER)
        body = response.json()
        # me endpoint uses success_response which injects request_id from ctx var
        assert body["request_id"] == response.headers["x-request-id"]


# ---------------------------------------------------------------------------
# Error format – shared model validation
# ---------------------------------------------------------------------------

class TestErrorFormat:
    def test_not_found_route_returns_404_standard_format(self):
        """FastAPI 404 for unknown routes should still follow error conventions."""
        response = client.get("/api/v1/does-not-exist")
        assert response.status_code == 404
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_401_error_has_correct_shape(self):
        response = client.get("/api/v1/me")
        body = response.json()
        assert_error_shape(body)

    def test_request_id_is_present_on_error_responses(self):
        response = client.get("/api/v1/me")  # no auth -> 401
        assert "request_id" in response.json()
