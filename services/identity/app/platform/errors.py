"""The error wire shape every service answers with: {"detail": {"code", "message", ...}}.

Raise `Problem` anywhere in a request; `install_error_handlers(app)` turns it into that
response, with the same field order the monolith used (code, message, extra..., field).
Request validation errors (422) keep FastAPI's own shape, exactly as the monolith did.
Losing the service's own database answers the gateway's 503 `service_unavailable`
(with Retry-After), so the front end says "try again in a moment" whether the whole
service is down or only its database.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

_errors = logging.getLogger("sgjio.errors")

# Byte for byte what the gateway answers when a service can't be reached.
UNAVAILABLE = {
    "code": "service_unavailable",
    "message": "SGJio is unavailable right now. Please try again in a moment.",
}
RETRY_AFTER_SECONDS = "5"


class Problem(Exception):
    """A rule the request broke. `status_code` is the HTTP status to answer with."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        field: str | None = None,
        extra: dict | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        self.extra = extra or {}
        self.headers = headers

    def detail(self) -> dict:
        detail = {"code": self.code, "message": self.message, **self.extra}
        if self.field:
            detail["field"] = self.field
        return detail


def not_signed_in() -> Problem:
    """The 401 every protected route gives, byte for byte as before the split."""
    return Problem("not_signed_in", "Please sign in to continue.", 401)


async def problem_handler(request: Request, problem: Problem) -> JSONResponse:
    return JSONResponse(
        {"detail": problem.detail()}, status_code=problem.status_code, headers=problem.headers
    )


async def database_unavailable_handler(request: Request, error: Exception) -> JSONResponse:
    """The database refused or dropped the connection (or a statement hit a transient
    failure such as a deadlock): nothing the client did, so say "try again" as a 503."""
    _errors.warning(
        "database unavailable",
        exc_info=error,
        extra={"fields": {"method": request.method, "path": request.url.path}},
    )
    return JSONResponse(
        {"detail": UNAVAILABLE},
        status_code=503,
        headers={"Retry-After": RETRY_AFTER_SECONDS},
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Problem, problem_handler)
    app.add_exception_handler(OperationalError, database_unavailable_handler)
    app.add_exception_handler(InterfaceError, database_unavailable_handler)
    # FastAPI's default, registered explicitly so the 422 shape is part of the contract.
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
