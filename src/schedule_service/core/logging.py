"""Structured JSON / readable logging and request_id context management."""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from collections.abc import Mapping
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any, Literal

from schedule_service.core.config import Settings, get_settings

REQUEST_ID_HEADER = "X-Request-ID"

_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "session",
    "credential",
    "api_key",
    "apikey",
)

_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_KV_SECRET_RE = re.compile(
    r"(?i)\b("
    r"password|passwd|password_hash|secret|token|access_token|refresh_token|"
    r"token_hash|authorization|cookie|session|session_id|api_key|apikey"
    r")\b(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)

_STANDARD_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "request_id",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

request_id_ctx_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the current request_id from contextvars, or None outside a request."""
    return request_id_ctx_var.get()


def set_request_id(request_id: str | None) -> Token[str | None]:
    """Bind request_id in contextvars and return the reset token."""
    return request_id_ctx_var.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore previous request_id context value using the reset token."""
    request_id_ctx_var.reset(token)


def resolve_request_id(incoming: str | None) -> str:
    """Safely validate an incoming X-Request-ID or generate a fresh UUID4.

    Accepts only ASCII alphanumeric characters plus ``.``, ``_``, and ``-`` up to
    128 characters to prevent header injection and log forging.
    """
    if incoming is not None:
        candidate = incoming.strip()
        if _SAFE_REQUEST_ID_RE.fullmatch(candidate):
            return candidate
    return str(uuid.uuid4())


def is_sensitive_key(key: str) -> bool:
    """Return True if a structured log field name may hold secrets or sessions."""
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def sanitize_string(value: str) -> str:
    """Redact bearer tokens and inline credential key-value pairs from text."""
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", value)
    return _KV_SECRET_RE.sub(r"\1\2[REDACTED]", redacted)


def sanitize_value(value: Any) -> Any:
    """Recursively drop sensitive keys and redact secrets from log values."""
    if isinstance(value, str):
        return sanitize_string(value)
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item) for item in value]
    return value


def sanitize_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``data`` with sensitive keys excluded and strings sanitized."""
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        key_str = str(key)
        if is_sensitive_key(key_str):
            continue
        sanitized[key_str] = sanitize_value(value)
    return sanitized


def _extract_extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Extract and sanitize non-standard structured fields from a LogRecord."""
    raw_extras = {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_")
    }
    return sanitize_mapping(raw_extras)


class RequestIdFilter(logging.Filter):
    """Attach the active contextvars request_id to every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) is None:
            record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON with request_id and secret filtering."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        request_id = getattr(record, "request_id", None) or get_request_id()
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_string(record.getMessage()),
            "request_id": request_id,
        }
        payload.update(_extract_extra_fields(record))
        if record.exc_info:
            payload["exception"] = sanitize_string(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class ReadableFormatter(logging.Formatter):
    """Format log records as human-readable lines for local development."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        request_id = getattr(record, "request_id", None) or get_request_id() or "-"
        message = sanitize_string(record.getMessage())
        extras = _extract_extra_fields(record)
        extras_suffix = ""
        if extras:
            formatted_pairs = " ".join(f"{key}={value}" for key, value in extras.items())
            extras_suffix = f" | {formatted_pairs}"
        line = (
            f"{timestamp} {record.levelname} [req={request_id}] "
            f"{record.name}: {message}{extras_suffix}"
        )
        if record.exc_info:
            exception_text = sanitize_string(self.formatException(record.exc_info))
            line = f"{line}\n{exception_text}"
        return line


def resolve_log_format(settings: Settings) -> Literal["json", "text"]:
    """Resolve effective log format from settings (text in local/dev, json otherwise)."""
    if settings.log_format in ("json", "text"):
        return settings.log_format
    if settings.environment.strip().lower() in {"development", "local"}:
        return "text"
    return "json"


def _resolve_log_level(level_name: str) -> int:
    """Convert log level string into a standard logging numeric level."""
    numeric = getattr(logging, level_name.strip().upper(), None)
    if isinstance(numeric, int):
        return numeric
    return logging.INFO


def configure_logging(settings: Settings | None = None) -> None:
    """Configure application logging with JSON or readable formatter and request_id filter."""
    active_settings = settings or get_settings()
    effective_format = resolve_log_format(active_settings)
    level = _resolve_log_level(active_settings.log_level)

    formatter: logging.Formatter = (
        JsonFormatter() if effective_format == "json" else ReadableFormatter()
    )
    request_id_filter = RequestIdFilter()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Replace plain StreamHandlers while preserving pytest LogCaptureHandler or custom handlers.
    for existing in list(root_logger.handlers):
        if type(existing) is logging.StreamHandler:
            root_logger.removeHandler(existing)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(request_id_filter)
    root_logger.addHandler(stream_handler)

    app_logger = logging.getLogger("schedule_service")
    app_logger.setLevel(level)
    app_logger.propagate = True
    app_logger.filters = [f for f in app_logger.filters if not isinstance(f, RequestIdFilter)]
    app_logger.addFilter(request_id_filter)

    # Avoid duplicate non-JSON Uvicorn access lines when JSON logging is enabled;
    # RequestContextMiddleware emits structured HTTP access logs with request_id.
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.disabled = effective_format == "json"
