#!/usr/bin/env python3
"""
End-to-end backend checker for Stocklytics AI.

Usage:
    python backend/scripts/run_backend_e2e_check.py

It loads backend/.env automatically, calls the running API, and validates:
    - platform endpoints
    - inventory flow
    - customer flow
    - billing idempotency and insufficient-stock failure
    - alerts summary/list
    - optional pipeline trigger/poll
    - optional analytics and AI endpoints
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
ENV_PATH = BACKEND_DIR / ".env"

load_dotenv(ENV_PATH)


class CheckFailure(RuntimeError):
    """Raised when an E2E step fails."""


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise CheckFailure(f"Missing required environment variable: {name}")
    return value or ""


BASE_URL = env("BASE_URL", "http://127.0.0.1:8000", required=True).rstrip("/")
TOKEN = env("TEST_BEARER_TOKEN", required=True)
STORE_ID = env("TEST_STORE_ID", required=True)
PAYMENT_METHOD = env("TEST_PAYMENT_METHOD", "cash", required=True)
RUN_PIPELINE_CHECK = env("RUN_PIPELINE_CHECK", "0") == "1"
RUN_ANALYTICS_AI_CHECK = env("RUN_ANALYTICS_AI_CHECK", "0") == "1"
CHAT_QUERY = env("TEST_CHAT_QUERY", "Give me a short business summary for today.")
CHAT_SESSION_ID = env("TEST_CHAT_SESSION_ID", "") or f"chat_e2e_{uuid.uuid4().hex[:8]}"


def log(step: str, message: str) -> None:
    print(f"[{step}] {message}")


def require_status(response: httpx.Response, expected: int, step: str) -> dict[str, Any]:
    if response.status_code != expected:
        raise CheckFailure(
            f"{step} failed: expected HTTP {expected}, got {response.status_code}. "
            f"Body: {response.text}"
        )
    return response.json()


def require_key(body: dict[str, Any], key: str, step: str) -> Any:
    if key not in body:
        raise CheckFailure(f"{step} failed: missing key '{key}' in response: {body}")
    return body[key]


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def is_error_shape(body: dict[str, Any]) -> bool:
    return "request_id" in body and "error" in body


def maybe_print_skip(step: str, message: str) -> None:
    log(step, f"SKIP: {message}")


def run() -> None:
    seed = uuid.uuid4().hex[:8]
    customer_phone = f"+9199{seed[:8]}"
    product_a_name = f"E2E Rice {seed}"
    product_b_name = f"E2E Biscuit {seed}"
    idempotency_key = f"bill_e2e_{seed}"

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        log("platform", f"Using {BASE_URL}")

        body = require_status(client.get("/api/v1/health"), 200, "health")
        if body.get("status") != "ok":
            raise CheckFailure(f"health failed: unexpected body {body}")
        log("platform", "health OK")

        ready = client.get("/api/v1/ready")
        if ready.status_code == 200:
            log("platform", f"ready OK: {ready.json()}")
        elif ready.status_code == 503:
            log("platform", f"ready returned 503: {ready.json()}")
        else:
            raise CheckFailure(f"ready failed unexpectedly: {ready.status_code} {ready.text}")

        me = require_status(client.get("/api/v1/me", headers=auth_headers()), 200, "me")
        user = require_key(me, "user", "me")
        if user.get("store_id") != STORE_ID:
            raise CheckFailure(f"me failed: token store_id {user.get('store_id')} != TEST_STORE_ID {STORE_ID}")
        log("platform", f"authenticated as {user.get('user_id')} in {STORE_ID}")

        customer_payload = {
            "store_id": STORE_ID,
            "name": f"E2E Customer {seed}",
            "phone": customer_phone,
        }
        customer = require_status(
            client.post("/api/v1/customers", json=customer_payload, headers=auth_headers()),
            201,
            "create_customer",
        )
        customer_id = require_key(customer["customer"], "customer_id", "create_customer")
        log("customer", f"created {customer_id}")

        product_a = require_status(
            client.post(
                "/api/v1/inventory/products",
                json={
                    "store_id": STORE_ID,
                    "name": product_a_name,
                    "price": 320.0,
                    "quantity": 6,
                    "reorder_threshold": 4,
                    "category": "Grocery",
                },
                headers=auth_headers(),
            ),
            201,
            "create_product_a",
        )["product"]
        product_b = require_status(
            client.post(
                "/api/v1/inventory/products",
                json={
                    "store_id": STORE_ID,
                    "name": product_b_name,
                    "price": 35.0,
                    "quantity": 20,
                    "reorder_threshold": 5,
                    "category": "Snacks",
                },
                headers=auth_headers(),
            ),
            201,
            "create_product_b",
        )["product"]
        product_a_id = product_a["product_id"]
        product_b_id = product_b["product_id"]
        log("inventory", f"created {product_a_id} and {product_b_id}")

        listed = require_status(
            client.get("/api/v1/inventory/products", headers=auth_headers()),
            200,
            "list_products",
        )
        item_ids = {item["product_id"] for item in listed.get("items", [])}
        if product_a_id not in item_ids or product_b_id not in item_ids:
            raise CheckFailure("list_products failed: created products not found in list response")
        log("inventory", "list OK")

        updated = require_status(
            client.patch(
                f"/api/v1/inventory/products/{product_a_id}",
                json={
                    "store_id": STORE_ID,
                    "price": 330.0,
                    "reorder_threshold": 3,
                },
                headers=auth_headers(),
            ),
            200,
            "update_product",
        )["product"]
        if updated.get("price") != 330.0:
            raise CheckFailure(f"update_product failed: unexpected body {updated}")
        log("inventory", "update OK")

        adjusted = require_status(
            client.post(
                f"/api/v1/inventory/products/{product_b_id}/stock-adjustments",
                json={
                    "store_id": STORE_ID,
                    "adjustment_type": "ADD",
                    "quantity_delta": 5,
                    "reason": "E2E top-up",
                },
                headers=auth_headers(),
            ),
            200,
            "stock_adjustment",
        )
        if adjusted.get("new_quantity_on_hand") != 25:
            raise CheckFailure(f"stock_adjustment failed: unexpected body {adjusted}")
        log("inventory", "stock adjustment OK")

        billing_payload = {
            "store_id": STORE_ID,
            "idempotency_key": idempotency_key,
            "customer_id": customer_id,
            "payment_method": PAYMENT_METHOD,
            "items": [
                {"product_id": product_a_id, "quantity": 4},
                {"product_id": product_b_id, "quantity": 2},
            ],
        }
        billed = require_status(
            client.post("/api/v1/billing/transactions", json=billing_payload, headers=auth_headers()),
            201,
            "billing_success",
        )
        transaction_id = billed["transaction"]["transaction_id"]
        log("billing", f"created transaction {transaction_id}")

        replay = require_status(
            client.post("/api/v1/billing/transactions", json=billing_payload, headers=auth_headers()),
            200,
            "billing_replay",
        )
        if replay.get("idempotent_replay") is not True:
            raise CheckFailure(f"billing_replay failed: expected idempotent_replay=true, got {replay}")
        log("billing", "idempotent replay OK")

        insufficient = client.post(
            "/api/v1/billing/transactions",
            json={
                "store_id": STORE_ID,
                "idempotency_key": f"bill_fail_{seed}",
                "payment_method": PAYMENT_METHOD,
                "items": [{"product_id": product_a_id, "quantity": 9999}],
            },
            headers=auth_headers(),
        )
        insufficient_body = require_status(insufficient, 409, "billing_insufficient_stock")
        if insufficient_body["error"]["code"] != "INSUFFICIENT_STOCK":
            raise CheckFailure(f"billing_insufficient_stock failed: unexpected body {insufficient_body}")
        log("billing", "insufficient stock path OK")

        customer_detail = require_status(
            client.get(f"/api/v1/customers/{customer_id}", headers=auth_headers()),
            200,
            "customer_detail",
        )["customer"]
        if float(customer_detail.get("total_spend", 0.0)) <= 0:
            raise CheckFailure(f"customer_detail failed: summary not updated {customer_detail}")
        log("customer", "summary update OK")

        history = require_status(
            client.get(f"/api/v1/customers/{customer_id}/purchase-history", headers=auth_headers()),
            200,
            "purchase_history",
        )
        history_ids = {item["transaction_id"] for item in history.get("transactions", [])}
        if transaction_id not in history_ids:
            raise CheckFailure(f"purchase_history failed: transaction {transaction_id} not found")
        log("customer", "purchase history OK")

        alerts_summary = require_status(
            client.get("/api/v1/alerts/summary", headers=auth_headers()),
            200,
            "alerts_summary",
        )
        log("alerts", f"summary {alerts_summary['summary']}")

        alerts = require_status(
            client.get("/api/v1/alerts/", headers=auth_headers()),
            200,
            "alerts_list",
        )
        log("alerts", f"list returned {len(alerts.get('items', []))} items")

        if RUN_PIPELINE_CHECK:
            triggered = require_status(
                client.post(
                    "/api/v1/pipeline/runs/sync",
                    json={"store_id": STORE_ID, "trigger_mode": "manual"},
                    headers=auth_headers(),
                ),
                202,
                "pipeline_trigger",
            )
            pipeline_run_id = triggered["pipeline_run_id"]
            log("pipeline", f"triggered {pipeline_run_id}")

            deadline = time.time() + 120
            final_status = None
            while time.time() < deadline:
                polled = require_status(
                    client.get(f"/api/v1/pipeline/runs/{pipeline_run_id}", headers=auth_headers()),
                    200,
                    "pipeline_poll",
                )
                final_status = polled["pipeline_run"]["status"]
                if final_status in {"SUCCEEDED", "FAILED"}:
                    break
                time.sleep(3)

            if final_status not in {"SUCCEEDED", "FAILED"}:
                raise CheckFailure("pipeline_poll failed: run did not reach terminal state in time")
            log("pipeline", f"final status {final_status}")

            failures = require_status(
                client.get("/api/v1/pipeline/failures", headers=auth_headers()),
                200,
                "pipeline_failures",
            )
            log("pipeline", f"failures endpoint returned {len(failures.get('items', []))} items")
        else:
            maybe_print_skip("pipeline", "set RUN_PIPELINE_CHECK=1 to test pipeline endpoints")

        if RUN_ANALYTICS_AI_CHECK:
            dashboard = client.get("/api/v1/analytics/dashboard", headers=auth_headers())
            if dashboard.status_code == 200:
                log("analytics", f"dashboard OK: freshness={dashboard.json().get('freshness_status')}")
            else:
                raise CheckFailure(f"analytics dashboard failed: {dashboard.status_code} {dashboard.text}")

            trends = require_status(
                client.get("/api/v1/analytics/sales-trends", headers=auth_headers()),
                200,
                "analytics_trends",
            )
            log("analytics", f"sales trends points={len(trends.get('points', []))}")

            performance = require_status(
                client.get("/api/v1/analytics/product-performance", headers=auth_headers()),
                200,
                "analytics_product_performance",
            )
            log("analytics", f"product performance items={len(performance.get('items', []))}")

            customers = require_status(
                client.get("/api/v1/analytics/customer-insights", headers=auth_headers()),
                200,
                "analytics_customer_insights",
            )
            log("analytics", f"customer insights items={len(customers.get('top_customers', []))}")

            chat = require_status(
                client.post(
                    "/api/v1/ai/chat",
                    json={
                        "store_id": STORE_ID,
                        "chat_session_id": CHAT_SESSION_ID,
                        "query": CHAT_QUERY,
                    },
                    headers=auth_headers(),
                ),
                200,
                "ai_chat",
            )
            log("ai", f"chat OK: freshness={chat.get('freshness_status')}")

            session = require_status(
                client.get(f"/api/v1/ai/chat/sessions/{CHAT_SESSION_ID}", headers=auth_headers()),
                200,
                "ai_session",
            )
            log("ai", f"session messages={len(session.get('messages', []))}")
        else:
            maybe_print_skip("analytics/ai", "set RUN_ANALYTICS_AI_CHECK=1 after pipeline/marts are ready")

    log("done", "backend E2E check completed successfully")


if __name__ == "__main__":
    try:
        run()
    except CheckFailure as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"[FAIL] HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
