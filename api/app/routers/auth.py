"""Sign-in, sign-out and "who am I" for the main app and the admin portal.

The same routes are mounted twice: at /api/auth for the main app and at /api/admin/auth
for the admin portal. Each uses its own cookie and its own sessions, so the two never
mix. The sign-in pages themselves are built in SCRUM-62 and SCRUM-68.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.deps import require_admin, require_user
from app.auth.service import sign_in
from app.auth.sessions import (
    COOKIE_NAMES,
    clear_session_cookie,
    create_session,
    end_session,
    set_session_cookie,
)
from app.db import get_db
from app.models import AuthScope, User
from app.schemas import SignInRequest, SignInResponse, UserOut

INVALID_CREDENTIALS = {
    "code": "invalid_credentials",
    "message": "The email or password is incorrect.",
}


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

    @router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
    def sign_out_route(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
        end_session(db, request.cookies.get(COOKIE_NAMES[scope]), scope)
        clear_session_cookie(response, scope)

    @router.get("/me", response_model=UserOut, responses={401: {"description": "Signed out"}})
    def me_route(user: User = Depends(guard)) -> User:
        return user

    return router
