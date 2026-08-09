"""Structured JSON logging setup for the e-commerce API."""

import logging
import uuid

from pythonjsonlogger import jsonlogger

from app.config import settings


class RequestIdFilter(logging.Filter):
    """Inject a request_id field into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = str(uuid.uuid4())
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a JSON-formatted logger bound to *name*."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.addFilter(RequestIdFilter())
    logger.setLevel(settings.LOG_LEVEL)

    logger.extra = {"service": settings.APP_NAME}  # type: ignore[attr-defined]
    return logger


# Module-level logger used across the application
log = get_logger(settings.APP_NAME)
