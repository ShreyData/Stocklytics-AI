"""
Billing Module router stub.

Owned by: Billing Module developer.
Base path: /api/v1/billing

Planned endpoints (implement per billing_implementation.md):
    POST  /api/v1/billing/transactions
    GET   /api/v1/billing/transactions
    GET   /api/v1/billing/transactions/{transaction_id}

Key rules:
    - Billing is strictly atomic.
    - Every create request must include idempotency_key.
    - Same key + same payload  -> return original result (idempotent replay).
    - Same key + diff payload  -> return 409 IDEMPOTENCY_KEY_CONFLICT.
"""

from fastapi import APIRouter

router = APIRouter()

# TODO: implement billing endpoints per billing_implementation.md and api_contracts.md
