"""
Request-ID middleware.

Generates a unique request_id for every incoming HTTP request, stores it in
a context variable (so every log line in that request automatically includes it),
and adds it to the response headers for client-side traceability.
"""

import uuid
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.common.logging_config import request_id_ctx_var

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Generates a unique request_id (format: req_<uuid4_hex_short>).
    2. Sets it into the request_id_ctx_var context variable.
    3. Injects it into the response via X-Request-ID header.
    4. Logs basic request/response info with timing.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = f"req_{uuid.uuid4().hex[:16]}"
        token = request_id_ctx_var.set(request_id)
        start_time = time.perf_counter()
        response: Response | None = None

        logger.info(
            "Incoming request",
            extra={
                "method": request.method,
                "path": request.url.path,
            },
        )

        try:
            response = await call_next(request)
        finally:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code if response is not None else None,
                    "elapsed_ms": elapsed_ms,
                },
            )
            request_id_ctx_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response
