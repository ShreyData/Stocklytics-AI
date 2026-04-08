"""
Logging configuration for RetailMind AI.
Structured JSON logging ensuring request_id and other key IDs appear in every log record.
"""

import logging
import json
import sys
from contextvars import ContextVar

# Context variable holding the current request_id so it is automatically
# included in every log line emitted during a request lifecycle.
request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_object = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx_var.get("-"),
        }
        # Attach any extra keys passed via logger.info("msg", extra={...}).
        # The set below contains every standard LogRecord attribute that must
        # NOT be overwritten or re-emitted as an extra field.
        _RESERVED = {
            "name", "msg", "args", "levelname", "levelno",
            "pathname", "filename", "module", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread",
            "threadName", "processName", "process", "message",
            "taskName", "request_id",
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                log_object[key] = value

        if record.exc_info:
            log_object["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_object, default=str)


def configure_logging(level: str = "INFO") -> None:
    """
    Set up root logger with JSON formatting.
    Call once at application startup in main.py.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
