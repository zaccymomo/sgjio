"""JSON logs and the correlation id.

`configure_logging()` makes every log line one JSON object carrying the service name and
the current request's id, at the level in LOG_LEVEL (default INFO).
`CorrelationIdMiddleware` takes X-Request-ID from the request (the gateway always sends
one), or makes one, keeps it in `correlation_id` for the request (so events emitted while
handling it carry it), and returns it on the response.
An unhandled exception is logged (with the request id) and answered here with a 500 that
also carries X-Request-ID; the body is Starlette's usual "Internal Server Error".
"""

import json
import logging
import os
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from .config import get_config

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_access = logging.getLogger("sgjio.access")
_errors = logging.getLogger("sgjio.errors")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": get_config().service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": correlation_id.get(),
        }
        line.update(getattr(record, "fields", {}))
        if record.exc_info:
            line["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def configure_logging(level: str | None = None) -> None:
    level = level or os.environ.get("LOG_LEVEL") or "INFO"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # One access line per request comes from the middleware below instead.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("pika").setLevel(logging.WARNING)


class CorrelationIdMiddleware:
    """Plain ASGI middleware (not BaseHTTPMiddleware), so streaming responses and context
    variables behave normally."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        given = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = given if _SAFE_ID.match(given) else uuid.uuid4().hex
        token = correlation_id.set(request_id)
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_id(message):
            nonlocal status
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            # Inside this middleware the request id is still set, so the traceback line
            # carries it, and the 500 gets the X-Request-ID header like any other answer.
            _errors.exception("unhandled error in %s %s", scope["method"], scope["path"])
            if response_started:
                raise  # too late to answer; the server closes the connection
            status = 500
            await send_with_id(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"text/plain; charset=utf-8"),
                        (b"content-length", b"21"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b"Internal Server Error"})
        finally:
            # Health checks run every few seconds; logging them would drown everything else.
            level = logging.DEBUG if scope["path"].startswith("/health/") else logging.INFO
            _access.log(
                level,
                "%s %s %s",
                scope["method"],
                scope["path"],
                status,
                extra={
                    "fields": {
                        "method": scope["method"],
                        "path": scope["path"],
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
            correlation_id.reset(token)
