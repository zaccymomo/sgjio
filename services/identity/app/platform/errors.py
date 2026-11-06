"""The error wire shape every service answers with: {"detail": {"code", "message", ...}}.

Raise `Problem` anywhere in a request; `install_error_handlers(app)` turns it into that
response, with the same field order the monolith used (code, message, extra..., field).
Request validation errors (422) keep FastAPI's own shape, exactly as the monolith did.
"""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Problem, problem_handler)
    # FastAPI's default, registered explicitly so the 422 shape is part of the contract.
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
