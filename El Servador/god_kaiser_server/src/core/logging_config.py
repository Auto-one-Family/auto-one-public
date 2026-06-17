"""
Structured Logging Setup mit JSON-Format und File-Rotation

Optional structured field ``failure_class`` (I08 pilot): small string enum for error
taxonomy in JSON file logs. Set via ``logger.*(..., extra={"failure_class": "<value>"})``.
Values must not contain PII (no free-form user text). Pilot set:

- ``mqtt_json_parse`` — MQTT payload is not valid JSON (subscriber).
- ``mqtt_route`` — uncaught exception while routing an MQTT message (subscriber).
- ``sensor_payload_validation`` — sensor handler rejected payload (validation).

Additional keys can be allowlisted in ``_STRUCTURED_JSON_FIELDS`` when needed.

Notification / Alert Center (additive observability, no PII):

- ``notification_id`` — UUID string of the persisted notification row.
- ``alert_status`` — ISA-18.2 lifecycle status (e.g. ``active``, ``acknowledged``, ``resolved``).
- ``ws_event_type`` — Realtime fan-out event name (e.g. ``notification_new``) or omitted on pure REST logs.
"""

import json
import logging
import logging.handlers
import sys
import time
from pathlib import Path
from typing import Any, Dict

from .config import get_settings
from .request_context import get_request_id, get_traceparent

# Keys copied from LogRecord into JSON log lines (set via logging ``extra=``).
# Keep minimal: arbitrary LogRecord attrs are not merged (reserved / collision risk).
_STRUCTURED_JSON_FIELDS: tuple[str, ...] = (
    "failure_class",
    "notification_id",
    "alert_status",
    "ws_event_type",
)


class RequestIdFilter(logging.Filter):
    """Filter that adds request_id (and optional traceparent) to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        tp = get_traceparent()
        record.traceparent = tp if tp else "-"
        return True


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    converter = time.gmtime  # All timestamps in UTC

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            str: JSON-formatted log message
        """
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request_id for request correlation
        request_id = getattr(record, "request_id", "-")
        if request_id and request_id != "-":
            log_data["request_id"] = request_id

        traceparent = getattr(record, "traceparent", "-")
        if traceparent and traceparent != "-":
            log_data["traceparent"] = traceparent

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Optional structured fields (passed via logger's extra= dict → LogRecord attrs)
        for key in _STRUCTURED_JSON_FIELDS:
            if hasattr(record, key):
                val = getattr(record, key)
                if val is not None and val != "":
                    log_data[key] = val

        # Legacy: nested dict on record.extra (rare; prefer extra= keys above)
        if hasattr(record, "extra") and isinstance(getattr(record, "extra"), dict):
            log_data.update(record.extra)

        return json.dumps(log_data, default=str)


class TextFormatter(logging.Formatter):
    """Standard text formatter for human-readable logs (stdout/Docker)."""

    converter = time.gmtime  # All timestamps in UTC

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as text.

        Args:
            record: Log record to format

        Returns:
            str: Formatted log message
        """
        # Ensure request_id / traceparent exist to avoid formatting errors
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        if not hasattr(record, "traceparent"):
            record.traceparent = "-"
        line = super().format(record)
        tp = getattr(record, "traceparent", "-")
        if tp and tp != "-":
            line = f"{line} traceparent={tp}"
        fc = getattr(record, "failure_class", None)
        if fc:
            line = f"{line} failure_class={fc}"
        for key in ("notification_id", "alert_status", "ws_event_type"):
            val = getattr(record, key, None)
            if val:
                line = f"{line} {key}={val}"
        return line


def setup_logging() -> None:
    """
    Setup logging configuration based on settings.

    Creates log directory if it doesn't exist and configures
    file and console handlers with appropriate formatters.
    """
    # Bug Z Fix: Windows Console kann keine Unicode-Zeichen (Emojis, Pfeile) darstellen
    # Ersetze nicht darstellbare Zeichen durch '?' statt einen UnicodeEncodeError zu werfen
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(errors="replace")
            sys.stderr.reconfigure(errors="replace")
        except AttributeError:
            # Python < 3.7 hat kein reconfigure()
            pass

    settings = get_settings()

    # Create logs directory
    log_path = Path(settings.logging.file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.logging.level))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Add request_id filter to root logger (applies to all handlers)
    root_logger.addFilter(RequestIdFilter())

    # Create formatters
    if settings.logging.format == "json":
        formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%SZ")
    else:
        formatter = TextFormatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # File handler with rotation (graceful fallback if log dir not writable)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=settings.logging.file_path,
            maxBytes=settings.logging.file_max_bytes,
            backupCount=settings.logging.file_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, settings.logging.level))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        # In CI/Docker the log directory may not be writable — fall back to stderr
        fallback = logging.StreamHandler(sys.stderr)
        fallback.setLevel(getattr(logging, settings.logging.level))
        fallback.setFormatter(formatter)
        root_logger.addHandler(fallback)
        print(
            f"WARNING: Could not create file handler for {settings.logging.file_path}: {e}. "
            f"Logging to stderr instead.",
            file=sys.stderr,
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.logging.level))

    # Use text formatter for console (easier to read)
    console_formatter = TextFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Reduce noise from external libraries
    logging.getLogger("paho.mqtt").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)

    root_logger.info(
        f"Logging configured: level={settings.logging.level}, "
        f"format={settings.logging.format}, file={settings.logging.file_path}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)
