"""
Alerts Module – Test suite.

Tests for the Alerts endpoints:
    - Happy path: list alerts, get summary
    - Lifecycle: acknowledge alert (ACTIVE -> ACKNOWLEDGED)
    - Lifecycle: resolve alert from ACTIVE (ACTIVE -> RESOLVED)
    - Lifecycle: resolve alert from ACKNOWLEDGED (ACKNOWLEDGED -> RESOLVED)
    - Validation: cannot acknowledge an already-ACKNOWLEDGED alert (409)
    - Validation: cannot resolve an already-RESOLVED alert (409)
    - Not found: 404 on unknown alert_id
    - Auth: 401 when no Bearer token is provided

All tests run against the FastAPI TestClient with Firestore fully mocked
so that no external I/O is required. Dev-token stub auth is used throughout.

Run with:
    pytest backend/tests/test_alerts.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

AUTH_HEADER = {"Authorization": "Bearer dev-token"}
STORE_ID = "store_001"
FAKE_ALERT_ID = "alert_001"
FAKE_NOW = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_ALERT_ACTIVE: dict[str, Any] = {
    "alert_id": FAKE_ALERT_ID,
    "store_id": STORE_ID,
    "alert_type": "LOW_STOCK",
    "condition_key": f"LOW_STOCK_{FAKE_ALERT_ID}",
    "source_entity_id": "prod_rice_5kg",
    "status": "ACTIVE",
    "severity": "HIGH",
    "title": "Rice 5kg stock is low",
    "message": "Only 3 units left. Reorder soon.",
    "metadata": {"quantity_on_hand": 3, "reorder_threshold": 8},
    "created_at": FAKE_NOW.isoformat(),
    "acknowledged_at": None,
    "acknowledged_by": None,
    "resolved_at": None,
    "resolved_by": None,
    "resolution_note": None,
    "last_evaluated_at": FAKE_NOW.isoformat(),
}

SAMPLE_ALERT_ACKNOWLEDGED: dict[str, Any] = {
    **SAMPLE_ALERT_ACTIVE,
    "status": "ACKNOWLEDGED",
    "acknowledged_at": FAKE_NOW.isoformat(),
    "acknowledged_by": "dev_user_001",
}

SAMPLE_ALERT_RESOLVED: dict[str, Any] = {
    **SAMPLE_ALERT_ACKNOWLEDGED,
    "status": "RESOLVED",
    "resolved_at": FAKE_NOW.isoformat(),
    "resolved_by": "dev_user_001",
    "resolution_note": "New stock received",
}


def assert_error_shape(body: dict) -> None:
    """Assert the shared error response model is present."""
    assert "request_id" in body, "Missing request_id"
    assert "error" in body, "Missing error object"
    assert "code" in body["error"], "Missing error.code"
    assert "message" in body["error"], "Missing error.message"
    assert "details" in body["error"], "Missing error.details"


# ---------------------------------------------------------------------------
# Test Class 1: List alerts
# ---------------------------------------------------------------------------

class TestListAlerts:
    """GET /api/v1/alerts – list alerts for a store."""

    def test_list_alerts_returns_200(self):
        """A valid list request returns 200 OK."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[SAMPLE_ALERT_ACTIVE],
        ):
            response = client.get("/api/v1/alerts/", headers=AUTH_HEADER)

        assert response.status_code == 200

    def test_list_alerts_contains_request_id(self):
        """Response envelope must include request_id."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[SAMPLE_ALERT_ACTIVE],
        ):
            response = client.get("/api/v1/alerts/", headers=AUTH_HEADER)

        assert "request_id" in response.json()

    def test_list_alerts_items_key_present(self):
        """Response must contain a top-level 'items' list."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[SAMPLE_ALERT_ACTIVE],
        ):
            response = client.get("/api/v1/alerts/", headers=AUTH_HEADER)

        body = response.json()
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_list_alerts_empty_store_returns_empty_list(self):
        """A store with no alerts must return an empty items list."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = client.get("/api/v1/alerts/", headers=AUTH_HEADER)

        assert response.json()["items"] == []

    def test_list_alerts_requires_auth(self):
        """Requests without a Bearer token must receive 401."""
        response = client.get("/api/v1/alerts/")
        assert response.status_code == 401
        assert_error_shape(response.json())

    def test_list_alerts_invalid_status_filter_returns_400(self):
        """An unrecognised status filter must return 400."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = client.get(
                "/api/v1/alerts/?status=BANANA", headers=AUTH_HEADER
            )

        assert response.status_code == 400
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "INVALID_QUERY"

    def test_list_alerts_invalid_type_filter_returns_400(self):
        """An unrecognised alert_type filter must return 400."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = client.get(
                "/api/v1/alerts/?alert_type=MOOD_SWING", headers=AUTH_HEADER
            )

        assert response.status_code == 400
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "INVALID_QUERY"

    def test_list_alerts_invalid_severity_filter_returns_400(self):
        """An unrecognised severity filter must return 400."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = client.get(
                "/api/v1/alerts/?severity=EXTREME", headers=AUTH_HEADER
            )

        assert response.status_code == 400
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "INVALID_QUERY"

    def test_list_alerts_contract_shape(self):
        """List endpoint returns the approved compact alert list shape."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[SAMPLE_ALERT_ACTIVE],
        ):
            response = client.get("/api/v1/alerts/", headers=AUTH_HEADER)

        item = response.json()["items"][0]
        assert set(item.keys()) == {
            "alert_id",
            "alert_type",
            "status",
            "severity",
            "title",
            "message",
            "created_at",
            "acknowledged_at",
            "resolved_at",
        }

    def test_list_alerts_valid_status_filter_accepted(self):
        """Valid status=ACTIVE filter must not raise a validation error."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[SAMPLE_ALERT_ACTIVE],
        ):
            response = client.get(
                "/api/v1/alerts/?status=ACTIVE", headers=AUTH_HEADER
            )

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test Class 2: Alert summary
# ---------------------------------------------------------------------------

class TestAlertSummary:
    """GET /api/v1/alerts/summary – alert count cards."""

    def test_summary_returns_200(self):
        """Summary endpoint must return 200 OK."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[SAMPLE_ALERT_ACTIVE],
        ):
            response = client.get("/api/v1/alerts/summary", headers=AUTH_HEADER)

        assert response.status_code == 200

    def test_summary_contains_required_fields(self):
        """Summary must expose active, acknowledged, and resolved_today counts."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[SAMPLE_ALERT_ACTIVE],
        ):
            response = client.get("/api/v1/alerts/summary", headers=AUTH_HEADER)

        body = response.json()
        assert "summary" in body
        summary = body["summary"]
        assert "active" in summary
        assert "acknowledged" in summary
        assert "resolved_today" in summary

    def test_summary_counts_active_alert(self):
        """A single ACTIVE alert must increment the active count to 1."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[SAMPLE_ALERT_ACTIVE],
        ):
            response = client.get("/api/v1/alerts/summary", headers=AUTH_HEADER)

        assert response.json()["summary"]["active"] == 1
        assert response.json()["summary"]["acknowledged"] == 0

    def test_summary_counts_acknowledged_alert(self):
        """A single ACKNOWLEDGED alert must increment acknowledged count to 1."""
        with patch(
            "app.modules.alerts.service.repository.list_alerts",
            new_callable=AsyncMock,
            return_value=[SAMPLE_ALERT_ACKNOWLEDGED],
        ):
            response = client.get("/api/v1/alerts/summary", headers=AUTH_HEADER)

        body = response.json()["summary"]
        assert body["active"] == 0
        assert body["acknowledged"] == 1

    def test_summary_requires_auth(self):
        """Summary without a Bearer token must return 401."""
        response = client.get("/api/v1/alerts/summary")
        assert response.status_code == 401
        assert_error_shape(response.json())


# ---------------------------------------------------------------------------
# Test Class 3: Acknowledge alert
# ---------------------------------------------------------------------------

class TestAcknowledgeAlert:
    """POST /api/v1/alerts/{alert_id}/acknowledge – ACTIVE -> ACKNOWLEDGED."""

    def test_acknowledge_active_alert_returns_200(self):
        """Acknowledging an ACTIVE alert must return 200 OK."""
        with (
            patch(
                "app.modules.alerts.service.repository.get_alert_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACTIVE,
            ),
            patch(
                "app.modules.alerts.service.repository.update_alert",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACKNOWLEDGED,
            ),
            patch(
                "app.modules.alerts.service.repository.write_alert_event",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/acknowledge",
                json={"store_id": STORE_ID, "note": "Supplier contacted"},
                headers=AUTH_HEADER,
            )

        assert response.status_code == 200

    def test_acknowledge_returns_acknowledged_status(self):
        """Response alert must show status=ACKNOWLEDGED."""
        with (
            patch(
                "app.modules.alerts.service.repository.get_alert_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACTIVE,
            ),
            patch(
                "app.modules.alerts.service.repository.update_alert",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACKNOWLEDGED,
            ),
            patch(
                "app.modules.alerts.service.repository.write_alert_event",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/acknowledge",
                json={"store_id": STORE_ID},
                headers=AUTH_HEADER,
            )

        body = response.json()
        assert body["alert"]["status"] == "ACKNOWLEDGED"
        assert body["alert"]["acknowledged_by"] == "dev_user_001"

    def test_acknowledge_already_acknowledged_returns_409(self):
        """
        Acknowledging an ACKNOWLEDGED alert must return 409 INVALID_ALERT_TRANSITION.
        Only ACTIVE alerts can be acknowledged.
        """
        with patch(
            "app.modules.alerts.service.repository.get_alert_by_id",
            new_callable=AsyncMock,
            return_value=SAMPLE_ALERT_ACKNOWLEDGED,  # already ACKNOWLEDGED
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/acknowledge",
                json={"store_id": STORE_ID},
                headers=AUTH_HEADER,
            )

        assert response.status_code == 409
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "INVALID_ALERT_TRANSITION"

    def test_acknowledge_resolved_alert_returns_409(self):
        """
        Acknowledging a RESOLVED alert must return 409 – RESOLVED is terminal.
        """
        with patch(
            "app.modules.alerts.service.repository.get_alert_by_id",
            new_callable=AsyncMock,
            return_value=SAMPLE_ALERT_RESOLVED,
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/acknowledge",
                json={"store_id": STORE_ID},
                headers=AUTH_HEADER,
            )

        assert response.status_code == 409
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "INVALID_ALERT_TRANSITION"

    def test_acknowledge_unknown_alert_returns_404(self):
        """Acknowledging a non-existent alert_id must return 404."""
        with patch(
            "app.modules.alerts.service.repository.get_alert_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.post(
                "/api/v1/alerts/unknown_alert_xyz/acknowledge",
                json={"store_id": STORE_ID},
                headers=AUTH_HEADER,
            )

        assert response.status_code == 404
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "ALERT_NOT_FOUND"

    def test_acknowledge_requires_auth(self):
        """Acknowledge without Bearer token must return 401."""
        response = client.post(
            f"/api/v1/alerts/{FAKE_ALERT_ID}/acknowledge",
            json={"store_id": STORE_ID},
        )
        assert response.status_code == 401
        assert_error_shape(response.json())

    def test_acknowledge_requires_request_id_in_response(self):
        """Acknowledge response must include request_id in envelope."""
        with (
            patch(
                "app.modules.alerts.service.repository.get_alert_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACTIVE,
            ),
            patch(
                "app.modules.alerts.service.repository.update_alert",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACKNOWLEDGED,
            ),
            patch(
                "app.modules.alerts.service.repository.write_alert_event",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/acknowledge",
                json={"store_id": STORE_ID},
                headers=AUTH_HEADER,
            )

        assert "request_id" in response.json()


# ---------------------------------------------------------------------------
# Test Class 4: Resolve alert
# ---------------------------------------------------------------------------

class TestResolveAlert:
    """POST /api/v1/alerts/{alert_id}/resolve – ACTIVE/ACKNOWLEDGED -> RESOLVED."""

    def test_resolve_active_alert_returns_200(self):
        """Resolving an ACTIVE alert must return 200 OK (direct ACTIVE -> RESOLVED)."""
        with (
            patch(
                "app.modules.alerts.service.repository.get_alert_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACTIVE,
            ),
            patch(
                "app.modules.alerts.service.repository.update_alert",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_RESOLVED,
            ),
            patch(
                "app.modules.alerts.service.repository.write_alert_event",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/resolve",
                json={"store_id": STORE_ID, "resolution_note": "New stock received"},
                headers=AUTH_HEADER,
            )

        assert response.status_code == 200

    def test_resolve_acknowledged_alert_returns_200(self):
        """Resolving an ACKNOWLEDGED alert must return 200 OK."""
        with (
            patch(
                "app.modules.alerts.service.repository.get_alert_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACKNOWLEDGED,
            ),
            patch(
                "app.modules.alerts.service.repository.update_alert",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_RESOLVED,
            ),
            patch(
                "app.modules.alerts.service.repository.write_alert_event",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/resolve",
                json={"store_id": STORE_ID, "resolution_note": "Stock arrived"},
                headers=AUTH_HEADER,
            )

        assert response.status_code == 200

    def test_resolve_returns_resolved_status(self):
        """Response alert must show status=RESOLVED."""
        with (
            patch(
                "app.modules.alerts.service.repository.get_alert_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACTIVE,
            ),
            patch(
                "app.modules.alerts.service.repository.update_alert",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_RESOLVED,
            ),
            patch(
                "app.modules.alerts.service.repository.write_alert_event",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/resolve",
                json={"store_id": STORE_ID},
                headers=AUTH_HEADER,
            )

        body = response.json()
        assert body["alert"]["status"] == "RESOLVED"
        assert body["alert"]["resolved_by"] == "dev_user_001"

    def test_resolve_already_resolved_returns_409(self):
        """
        Resolving a RESOLVED alert must return 409 – RESOLVED is a terminal state.
        """
        with patch(
            "app.modules.alerts.service.repository.get_alert_by_id",
            new_callable=AsyncMock,
            return_value=SAMPLE_ALERT_RESOLVED,
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/resolve",
                json={"store_id": STORE_ID},
                headers=AUTH_HEADER,
            )

        assert response.status_code == 409
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "INVALID_ALERT_TRANSITION"

    def test_resolve_unknown_alert_returns_404(self):
        """Resolving a non-existent alert_id must return 404."""
        with patch(
            "app.modules.alerts.service.repository.get_alert_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.post(
                "/api/v1/alerts/unknown_xyz/resolve",
                json={"store_id": STORE_ID},
                headers=AUTH_HEADER,
            )

        assert response.status_code == 404
        assert_error_shape(response.json())
        assert response.json()["error"]["code"] == "ALERT_NOT_FOUND"

    def test_resolve_requires_auth(self):
        """Resolve without Bearer token must return 401."""
        response = client.post(
            f"/api/v1/alerts/{FAKE_ALERT_ID}/resolve",
            json={"store_id": STORE_ID},
        )
        assert response.status_code == 401
        assert_error_shape(response.json())

    def test_resolve_response_contains_resolution_note(self):
        """Resolution note provided in request must appear in the response alert."""
        resolved_with_note = {**SAMPLE_ALERT_RESOLVED, "resolution_note": "New stock received"}
        with (
            patch(
                "app.modules.alerts.service.repository.get_alert_by_id",
                new_callable=AsyncMock,
                return_value=SAMPLE_ALERT_ACTIVE,
            ),
            patch(
                "app.modules.alerts.service.repository.update_alert",
                new_callable=AsyncMock,
                return_value=resolved_with_note,
            ),
            patch(
                "app.modules.alerts.service.repository.write_alert_event",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            response = client.post(
                f"/api/v1/alerts/{FAKE_ALERT_ID}/resolve",
                json={"store_id": STORE_ID, "resolution_note": "New stock received"},
                headers=AUTH_HEADER,
            )

        assert response.json()["alert"]["resolution_note"] == "New stock received"
