"""ASGI middleware for X-Request-ID propagation and structured HTTP request logging."""

from __future__ import annotations

import logging
import time

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from schedule_service.core.logging import (
    REQUEST_ID_HEADER,
    reset_request_id,
    resolve_request_id,
    set_request_id,
)

logger = logging.getLogger("schedule_service.http")


class RequestContextMiddleware:
    """Pure ASGI middleware managing X-Request-ID contextvars and HTTP request logs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = resolve_request_id(headers.get(REQUEST_ID_HEADER))
        token = set_request_id(request_id)

        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        start_time = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            status_code = 500
            logger.exception(
                "Unhandled exception during HTTP request",
                extra={
                    "event": "unhandled_exception",
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            if response_started:
                raise
            error_response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
                headers={REQUEST_ID_HEADER: request_id},
            )
            await error_response(scope, receive, send)
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if status_code >= 500:
                log_level = logging.ERROR
            elif status_code >= 400:
                log_level = logging.WARNING
            else:
                log_level = logging.INFO
            logger.log(
                log_level,
                "%s %s -> %s (%.2fms)",
                method,
                path,
                status_code,
                duration_ms,
                extra={
                    "event": "http_request",
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            reset_request_id(token)
