"""
Billing Module – FastAPI route handlers.

Base path (registered in main.py): /api/v1/billing
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.common.auth import AuthenticatedUser, require_auth
from app.common.responses import success_response
from app.modules.billing import service
from app.modules.billing.schemas import TransactionCreateRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/transactions", status_code=201)
async def create_transaction(
    payload: TransactionCreateRequest,
    user: AuthenticatedUser = Depends(require_auth),
):
    """
    Create a billing transaction.

    Idempotent replays return HTTP 200 with the original logical result.
    """
    result, status_code = await service.create_transaction(
        payload=payload,
        store_id=user.store_id,
        user_id=user.user_id,
    )
    return success_response(result, status_code=status_code)


@router.get("/transactions", status_code=200)
async def list_transactions(
    store_id: Optional[str] = Query(
        default=None,
        description="Store scope. Must match authenticated store_id when provided.",
    ),
    from_timestamp: Optional[datetime] = Query(
        default=None,
        alias="from",
        description="Return transactions on or after this ISO-8601 datetime.",
    ),
    to_timestamp: Optional[datetime] = Query(
        default=None,
        alias="to",
        description="Return transactions on or before this ISO-8601 datetime.",
    ),
    customer_id: Optional[str] = Query(
        default=None,
        description="Optional customer filter.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    page_token: Optional[str] = Query(default=None),
    user: AuthenticatedUser = Depends(require_auth),
):
    result = await service.list_transactions(
        store_id=user.store_id,
        requested_store_id=store_id,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        customer_id=customer_id,
        limit=limit,
        page_token=page_token,
    )
    return success_response(result)


@router.get("/transactions/{transaction_id}", status_code=200)
async def get_transaction(
    transaction_id: str,
    user: AuthenticatedUser = Depends(require_auth),
):
    transaction = await service.get_transaction(
        transaction_id=transaction_id,
        store_id=user.store_id,
    )
    return success_response({"transaction": transaction})
