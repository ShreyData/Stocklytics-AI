"""
Data Pipeline Module – Failure Handler.

Implements the retry loop described in data_pipeline_design.md §7:

    Attempt 1 – immediate retry
    Attempt 2 – retry after 1 minute
    Attempt 3 – retry after 5 minutes

After 3 failed attempts:
    - Mark pipeline_run as FAILED
    - Write exhausted batch into pipeline_failures (dead-letter)
    - Keep last successful checkpoint unchanged (do NOT advance it)

Usage:
    success, attempt_count, error = await run_with_retry(some_stage_fn, ...)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Backoff delays in seconds (data_pipeline_design.md §7)
_RETRY_DELAYS_SECONDS = [0, 60, 300]  # immediate, 1 min, 5 min
_MAX_ATTEMPTS = 3


async def run_with_retry(
    stage_fn: Callable[..., Coroutine[Any, Any, Any]],
    *,
    stage_name: str,
    pipeline_run_id: str,
    **kwargs: Any,
) -> tuple[bool, int, str]:
    """
    Run `stage_fn(**kwargs)` up to _MAX_ATTEMPTS times with backoff.

    Returns:
        (success: bool, attempt_count: int, error_message: str)

    - success=True means the stage completed without exception.
    - On failure, error_message contains the last exception string.
    - Caller is responsible for writing failure records after this returns False.
    """
    last_error = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        delay = _RETRY_DELAYS_SECONDS[attempt - 1]
        if delay > 0:
            logger.info(
                "Retrying stage after backoff",
                extra={
                    "pipeline_run_id": pipeline_run_id,
                    "stage_name": stage_name,
                    "attempt": attempt,
                    "delay_seconds": delay,
                },
            )
            await asyncio.sleep(delay)

        try:
            logger.info(
                "Running pipeline stage",
                extra={
                    "pipeline_run_id": pipeline_run_id,
                    "stage_name": stage_name,
                    "attempt": attempt,
                },
            )
            await stage_fn(**kwargs)
            logger.info(
                "Pipeline stage succeeded",
                extra={
                    "pipeline_run_id": pipeline_run_id,
                    "stage_name": stage_name,
                    "attempt": attempt,
                },
            )
            return True, attempt, ""

        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning(
                "Pipeline stage attempt failed",
                extra={
                    "pipeline_run_id": pipeline_run_id,
                    "stage_name": stage_name,
                    "attempt": attempt,
                    "error": last_error,
                },
            )

    logger.error(
        "Pipeline stage exhausted all retries",
        extra={
            "pipeline_run_id": pipeline_run_id,
            "stage_name": stage_name,
            "max_attempts": _MAX_ATTEMPTS,
            "final_error": last_error,
        },
    )
    return False, _MAX_ATTEMPTS, last_error
