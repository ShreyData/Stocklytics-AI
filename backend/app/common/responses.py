"""
Response helpers for Stocklytics AI.

Provides a consistent way to build success JSON responses so all routers
produce the same envelope shape without duplicating code.
"""

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.common.logging_config import request_id_ctx_var


def success_response(
    data: dict[str, Any],
    status_code: int = 200,
) -> JSONResponse:
    """
    Wrap a data payload in a success response.

    The request_id is injected automatically from the current request context.
    All response keys come from the caller – this helper only adds request_id.

    Example:
        return success_response({"product": product_dict}, status_code=201)

    Produces:
        {
            "request_id": "req_abc123",
            "product": { ... }
        }
    """
    request_id = request_id_ctx_var.get("-")
    body = {"request_id": request_id, **data}
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))
