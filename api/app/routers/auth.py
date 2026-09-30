"""Registering, signing in, signing out, password reset and "who am I" for both front ends.

The sign-in routes are mounted twice: at /api/auth for the main app and at
/api/admin/auth for the admin portal. Each uses its own cookie and its own sessions, so
the two never mix. Registration is mounted only for the main app, because administrator
accounts are made with `python -m app.cli create-admin` (SCRUM-68).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.deps import require_admin, require_user
from app.auth.reset import (
    check_reset_token,
    consume_reset_token,
    request_password_reset,
    set_new_password,
)
from app.auth.service import FieldProblem, new_password_problem, register, sign_in
from app.auth.sessions import (
    COOKIE_NAMES,
    clear_session_cookie,
    create_session,
    end_session,
    set_session_cookie,
)
from app.db import get_db
from app.models import AuthScope, User
from app.schemas import (
    ForgotPasswordRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetTokenRequest,
    SignInRequest,
    SignInResponse,
    UserOut,
)

INVALID_CREDENTIALS = {
    "code": "invalid_credentials",
    "message": "The email or password is incorrect.",
}

# A used, expired, cancelled or made-up link all look the same to the reader (SCRUM-63 AC6).
RESET_LINK_INVALID = {
    "code": "reset_link_invalid",
    "message": "This reset link is no longer valid. Request a new one.",
}

# An email already in use is a conflict; everything else registration refuses is the shape
# of what was sent, which is what 422 already means for this API.
REGISTER_PROBLEM_STATUS = {"email_taken": status.HTTP_409_CONFLICT}


def problem_error(problem: FieldProblem) -> HTTPException:
    """A refused form as an API error, naming the field to highlight."""
    detail = {"code": problem.code, "message": problem.message, "field": problem.field}
    if problem.failures:
        detail["failures"] = problem.failures
    refused = REGISTER_PROBLEM_STATUS.get(problem.code, status.HTTP_422_UNPROCESSABLE_CONTENT)
    return HTTPException(refused, detail=detail)


def build_auth_router(scope: AuthScope) -> APIRouter:
    router = APIRouter()
    guard = require_admin if scope == AuthScope.ADMIN else require_user

    @router.post(
        "/sign-in",
        response_model=SignInResponse,
        responses={
            401: {"description": "Wrong email or password"},
            429: {"description": "Temporarily blocked after repeated failures"},
        },
    )
    def sign_in_route(
        body: SignInRequest, request: Request, response: Response, db: Session = Depends(get_db)
    ) -> SignInResponse:
        ip_address = request.client.host if request.client else None
        result = sign_in(db, body.email, body.password, scope, ip_address)

        if result.blocked_until is not None:
            seconds = max(1, int((result.blocked_until - datetime.now(UTC)).total_seconds()))
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "too_many_attempts",
                    "message": "Too many failed sign-in attempts. Please try again later.",
                    "blocked_until": result.blocked_until.isoformat(),
                    "retry_after_seconds": seconds,
                },
                headers={"Retry-After": str(seconds)},
            )
        if not result.ok:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

        token, _ = create_session(db, result.user, scope)
        set_session_cookie(response, scope, token)
        return SignInResponse(user=UserOut.model_validate(result.user))

    if scope == AuthScope.APP:

        @router.post(
            "/register",
            response_model=RegisterResponse,
            status_code=status.HTTP_201_CREATED,
            responses={
                409: {"description": "That email is already registered"},
                422: {"description": "A field is missing, malformed, or the password is too weak"},
            },
        )
        def register_route(
            body: RegisterRequest, response: Response, db: Session = Depends(get_db)
        ) -> RegisterResponse:
            """Create an account and sign the new user in (SCRUM-61 AC1)."""
            result = register(
                db,
                name=body.name,
                email=body.email,
                password=body.password,
                password_confirmation=body.password_confirmation,
                user_type=body.user_type,
            )

            if result.problem is not None:
                # Which field to highlight (AC2-AC5).
                raise problem_error(result.problem)

            token, _ = create_session(db, result.user, scope)
            set_session_cookie(response, scope, token)
            return RegisterResponse(user=UserOut.model_validate(result.user))

    @router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
    def forgot_password_route(body: ForgotPasswordRequest, db: Session = Depends(get_db)) -> None:
        """Email a reset link if the account exists. The answer is the same either way."""
        request_password_reset(db, body.email, scope)

    @router.post(
        "/reset-password/check",
        status_code=status.HTTP_204_NO_CONTENT,
        responses={410: {"description": "The link was used, expired or replaced"}},
    )
    def check_reset_link_route(body: ResetTokenRequest, db: Session = Depends(get_db)) -> None:
        """Lets the page say straight away that a link is dead, before a password is typed."""
        if check_reset_token(db, body.token, scope) is None:
            raise HTTPException(status.HTTP_410_GONE, detail=RESET_LINK_INVALID)

    @router.post(
        "/reset-password",
        status_code=status.HTTP_204_NO_CONTENT,
        responses={
            410: {"description": "The link was used, expired or replaced"},
            422: {"description": "The passwords do not match or break a password rule"},
        },
    )
    def reset_password_route(body: ResetPasswordRequest, db: Session = Depends(get_db)) -> None:
        """Save a new password from a reset link and sign out everywhere (SCRUM-63 AC4-AC6)."""
        # Check the password before using up the link, so a typo does not cost the link.
        if check_reset_token(db, body.token, scope) is None:
            raise HTTPException(status.HTTP_410_GONE, detail=RESET_LINK_INVALID)
        problem = new_password_problem(body.password, body.password_confirmation)
        if problem is not None:
            raise problem_error(problem)
        user = consume_reset_token(db, body.token, scope)
        if user is None:
            raise HTTPException(status.HTTP_410_GONE, detail=RESET_LINK_INVALID)
        set_new_password(db, user, body.password)

    @router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
    def sign_out_route(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
        end_session(db, request.cookies.get(COOKIE_NAMES[scope]), scope)
        clear_session_cookie(response, scope)

    @router.get("/me", response_model=UserOut, responses={401: {"description": "Signed out"}})
    def me_route(user: User = Depends(guard)) -> User:
        return user

    return router
