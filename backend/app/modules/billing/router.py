"""
Billing Module – FastAPI route handlers.

Base path (registered in main.py): /api/v1/billing

Endpoints:
    POST  /transactions  – create a billing transaction (idempotent)

Routes are intentionally thin: all business logic is in service.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.common.auth import AuthenticatedUser, require_auth
from app.common.responses import success_response
from app.modules.billing import service
from app.modules.billing.schemas import TransactionCreateRequest

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/v1/billing/transactions
# ---------------------------------------------------------------------------

@router.post("/transactions", status_code=201)
async def create_transaction(
    payload: TransactionCreateRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """
    Create a billing transaction.

    - Validates stock for all items atomically (fail-fast, no partial writes).
    - Deducts stock and records audit trail inside a single Firestore transaction.
    - Idempotent: replaying the same idempotency_key + payload returns the
      original response (HTTP 200). A conflicting payload raises HTTP 409.
    """
    transaction, status_code = await service.create_transaction(
        payload=payload,
        store_id=user.store_id,
        user_id=user.user_id,
    )
    return success_response({"transaction": transaction}, status_code=status_code)
