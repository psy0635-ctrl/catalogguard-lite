"""CatalogGuard Lite structured logging helpers."""

import json
import logging


LOGGER_NAME = "catalogguard.api"
_HANDLER_MARKER = "_catalogguard_handler"
LogField = str | int | float | None
_UTC_FORMATTER = logging.Formatter(datefmt="%Y-%m-%dT%H:%M:%S")
_UTC_FORMATTER.converter = logging.time.gmtime


def _utc_timestamp() -> str:
    """Return the current UTC time in ISO-8601 format."""
    record = logging.LogRecord(
        name=LOGGER_NAME,
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    )
    timestamp = _UTC_FORMATTER.formatTime(record, _UTC_FORMATTER.datefmt)
    return f"{timestamp}.{int(record.msecs):03d}Z"


def configure_logging() -> logging.Logger:
    """Configure the project logger without duplicate handlers."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(
        getattr(handler, _HANDLER_MARKER, False) for handler in logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    *,
    event: str,
    **fields: LogField,
) -> None:
    """Write a one-line JSON event containing simple scalar fields."""
    payload: dict[str, LogField] = {
        "timestamp": _utc_timestamp(),
        "level": logging.getLevelName(level),
        "event": event,
    }
    payload.update(fields)
    logger.log(
        level,
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
