"""Registering, signing in, signing out, password reset and "who am I" for both front ends.

The sign-in routes are mounted twice: at /api/auth for the main app and at
/api/admin/auth for the admin portal. Each uses its own cookie and its own sessions, so
the two never mix. Registration is mounted only for the main app, because administrators
are invited from the portal instead (SCRUM-81), which mounts the invite routes.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import admins
from app.auth.deps import require_admin, require_user
from app.auth.google import (
    GoogleIdentity,
    GoogleSignup,
    GoogleTokenInvalid,
    GoogleUnavailable,
    sign_in_with_google,
    verify_google_token,
)
from app.auth.lockout import blocked_until, record_attempt
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
from app.models import AuthScope, AuthSession, LoginAttempt, PasswordResetToken, User
from app.privacy import NOTICE_VERSION
from app.schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    GoogleSignInRequest,
    GoogleSignInResponse,
    InviteOut,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetTokenRequest,
    SignInRequest,
    SignInResponse,
    UserOut,
)
from app.security import hash_password, hash_token, verify_password

INVALID_CREDENTIALS = {
    "code": "invalid_credentials",
    "message": "The email or password is incorrect.",
}
# A used, expired, cancelled or made-up link all look the same to the reader (SCRUM-63 AC6).
RESET_LINK_INVALID = {
    "code": "reset_link_invalid",
    "message": "This reset link is no longer valid. Request a new one.",
}

INVITE_LINK_INVALID = {
    "code": "invite_link_invalid",
    "message": "This invite link is no longer valid.",
}

GOOGLE_UNAVAILABLE = {
    "code": "google_sign_in_unavailable",
    "message": "Google sign-in isn't set up on this server. Use your email and password.",
}
GOOGLE_TOKEN_INVALID = {
    "code": "google_token_invalid",
    "message": "We couldn't confirm your Google sign-in. Please try again.",
}
# Which status each refusal from app.auth.google is sent with.
GOOGLE_REFUSAL_STATUS = {"privacy_notice_changed": status.HTTP_422_UNPROCESSABLE_CONTENT}

# An email already in use is a conflict; everything else registration refuses is the shape
# of what was sent, which is what 422 already means for this API.
REGISTER_PROBLEM_STATUS = {"email_taken": status.HTTP_409_CONFLICT}


def lockout_error(until: datetime) -> HTTPException:
    seconds = max(1, int((until - datetime.now(UTC)).total_seconds()))
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "too_many_attempts",
            "message": "Too many failed password attempts. Please try again later.",
            "blocked_until": until.isoformat(),
            "retry_after_seconds": seconds,
        },
        headers={"Retry-After": str(seconds)},
    )


def problem_error(problem: FieldProblem) -> HTTPException:
    """A refused form as an API error, naming the field to highlight."""
    detail = {"code": problem.code, "message": problem.message, "field": problem.field}
    if problem.failures:
        detail["failures"] = problem.failures
    refused = REGISTER_PROBLEM_STATUS.get(problem.code, status.HTTP_422_UNPROCESSABLE_CONTENT)
    return HTTPException(refused, detail=detail)


def google_identity(id_token: str) -> GoogleIdentity:
    """Who Google says this token is for, or the API error to send back."""
    try:
        return verify_google_token(id_token)
    except GoogleUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=GOOGLE_UNAVAILABLE
        ) from None
    except GoogleTokenInvalid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=GOOGLE_TOKEN_INVALID) from None


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
                privacy_notice_version=body.privacy_notice_version,
            )

            if result.problem is not None:
                # Which field to highlight (AC2-AC5).
                raise problem_error(result.problem)

            token, _ = create_session(db, result.user, scope)
            set_session_cookie(response, scope, token)
            return RegisterResponse(user=UserOut.model_validate(result.user))

        @router.post(
            "/google",
            response_model=GoogleSignInResponse,
            responses={
                401: {"description": "The Google token is invalid or expired"},
                403: {"description": "This account cannot be signed in to with Google"},
                422: {"description": "A sign-up field is missing, or the notice has changed"},
                503: {"description": "Google sign-in is not set up on this server"},
            },
        )
        def google_route(
            body: GoogleSignInRequest,
            request: Request,
            response: Response,
            db: Session = Depends(get_db),
        ) -> GoogleSignInResponse:
            """Continue with Google (SCRUM-92). Main app only: the portal never offers it.

            Signs in to the linked account, or links the learner account with the same
            verified email. Someone new gets `needs_signup` and nothing is created until
            the same token comes back with `signup` filled in.
            """
            identity = google_identity(body.id_token)
            signup = (
                GoogleSignup(
                    name=body.signup.name,
                    user_type=body.signup.user_type,
                    privacy_notice_version=body.signup.privacy_notice_version,
                )
                if body.signup
                else None
            )
            result = sign_in_with_google(db, identity, signup)

            if result.refusal is not None:
                refusal = result.refusal
                detail = {"code": refusal.code, "message": refusal.message}
                if refusal.code == "privacy_notice_changed":
                    detail["field"] = "privacy_consent"
                refused = GOOGLE_REFUSAL_STATUS.get(refusal.code, status.HTTP_403_FORBIDDEN)
                raise HTTPException(refused, detail=detail)
            if result.needs_signup:
                return GoogleSignInResponse(
                    status="needs_signup",
                    name=identity.name or identity.email.split("@")[0],
                    email=identity.email,
                )

            ip_address = request.client.host if request.client else None
            record_attempt(db, result.user.email, scope, succeeded=True, ip_address=ip_address)
            token, _ = create_session(db, result.user, scope)
            set_session_cookie(response, scope, token)
            return GoogleSignInResponse(
                status="signed_in",
                user=UserOut.model_validate(result.user),
                created=result.created,
            )

        @router.get("/privacy-notice-version")
        def privacy_notice_version_route() -> dict[str, str]:
            return {"version": NOTICE_VERSION}

        @router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
        def change_password_route(
            body: ChangePasswordRequest,
            request: Request,
            db: Session = Depends(get_db),
            user: User = Depends(require_user),
        ) -> None:
            """Keep this browser signed in; revoke all other sessions and reset links."""
            if not user.has_password:
                # Signed up with Google, so there is nothing to change (SCRUM-92).
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail={
                        "code": "no_password",
                        "message": "You sign in with Google, so there is no password to change.",
                    },
                )
            until = blocked_until(db, user.email, AuthScope.APP)
            if until is not None:
                raise lockout_error(until)
            if not verify_password(body.current_password, user.password_hash):
                record_attempt(
                    db,
                    user.email,
                    AuthScope.APP,
                    False,
                    request.client.host if request.client else None,
                )
                until = blocked_until(db, user.email, AuthScope.APP)
                if until is not None:
                    raise lockout_error(until)
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "code": "incorrect_current_password",
                        "field": "current_password",
                        "message": "Your current password is incorrect.",
                    },
                )
            record_attempt(
                db,
                user.email,
                AuthScope.APP,
                True,
                request.client.host if request.client else None,
            )
            problem = new_password_problem(body.password, body.password_confirmation)
            if problem is not None:
                raise problem_error(problem)
            token = request.cookies.get(COOKIE_NAMES[AuthScope.APP])
            user.password_hash = hash_password(body.password)
            db.execute(
                delete(AuthSession).where(
                    AuthSession.user_id == user.id,
                    AuthSession.token_hash != hash_token(token),
                )
            )
            db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
            db.commit()

        @router.post("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
        def delete_account_route(
            body: DeleteAccountRequest,
            response: Response,
            db: Session = Depends(get_db),
            user: User = Depends(require_user),
        ) -> None:
            """Delete a regular account and dependent personal data; never self-delete admins.

            Confirmed with the password, or with Google for an account that has none.
            """
            if user.is_admin:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "admin_self_delete_forbidden",
                        "message": "Administrator accounts cannot be deleted here.",
                    },
                )
            if user.has_password:
                if not body.password:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail={
                            "code": "password_required",
                            "field": "password",
                            "message": "Enter your password to confirm.",
                        },
                    )
                if not verify_password(body.password, user.password_hash):
                    raise HTTPException(
                        status.HTTP_401_UNAUTHORIZED,
                        detail={
                            "code": "incorrect_password",
                            "field": "password",
                            "message": "Your password is incorrect.",
                        },
                    )
            else:
                # No password to ask for: signing in with Google again confirms (SCRUM-92).
                if not body.id_token:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail={
                            "code": "google_confirmation_required",
                            "message": "Confirm with Google to delete your account.",
                        },
                    )
                if google_identity(body.id_token).sub != user.google_sub:
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN,
                        detail={
                            "code": "google_account_mismatch",
                            "message": (
                                "That's a different Google account from the one you use "
                                "for SGJio. Confirm with the same Google account."
                            ),
                        },
                    )
            db.execute(delete(LoginAttempt).where(LoginAttempt.email == user.email))
            db.delete(user)
            db.commit()
            clear_session_cookie(response, AuthScope.APP)

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

    if scope == AuthScope.ADMIN:

        @router.post(
            "/invite/check",
            response_model=InviteOut,
            responses={410: {"description": "Used, expired, replaced or already set up"}},
        )
        def check_invite_route(body: ResetTokenRequest, db: Session = Depends(get_db)) -> InviteOut:
            """Who an invite link is for, so the page can greet them (SCRUM-81)."""
            found = admins.invite_for_token(db, body.token)
            if found is None:
                raise HTTPException(status.HTTP_410_GONE, detail=INVITE_LINK_INVALID)
            admin, inviter = found
            return InviteOut(name=admin.name, email=admin.email, invited_by=inviter)

        @router.post(
            "/invite/accept",
            response_model=SignInResponse,
            responses={
                410: {"description": "Used, expired, replaced or already set up"},
                422: {"description": "The passwords do not match or break a password rule"},
            },
        )
        def accept_invite_route(
            body: ResetPasswordRequest,
            request: Request,
            response: Response,
            db: Session = Depends(get_db),
        ) -> SignInResponse:
            """Choose a first password from an invite, and sign straight in (SCRUM-81 AC2)."""
            if admins.invite_for_token(db, body.token) is None:
                raise HTTPException(status.HTTP_410_GONE, detail=INVITE_LINK_INVALID)
            problem = new_password_problem(body.password, body.password_confirmation)
            if problem is not None:
                raise problem_error(problem)
            user = consume_reset_token(db, body.token, scope)
            if user is None:
                raise HTTPException(status.HTTP_410_GONE, detail=INVITE_LINK_INVALID)
            set_new_password(db, user, body.password)
            # A sign-in like any other, so the Administrators page shows when it happened.
            ip_address = request.client.host if request.client else None
            record_attempt(db, user.email, scope, succeeded=True, ip_address=ip_address)
            token, _ = create_session(db, user, scope)
            set_session_cookie(response, scope, token)
            return SignInResponse(user=UserOut.model_validate(user))

    @router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
    def sign_out_route(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
        end_session(db, request.cookies.get(COOKIE_NAMES[scope]), scope)
        clear_session_cookie(response, scope)

    @router.get("/me", response_model=UserOut, responses={401: {"description": "Signed out"}})
    def me_route(user: User = Depends(guard)) -> User:
        return user

    return router
