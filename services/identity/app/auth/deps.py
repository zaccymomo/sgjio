"""FastAPI guards for protected routes.

Use them as dependencies:

    @router.get("/something")
    def something(user: User = Depends(require_user)): ...

    @router.get("/admin/something")
    def admin_thing(admin: User = Depends(require_admin)): ...

A signed-out request gets 401. The front ends turn a 401 into a redirect to their own
sign-in page, carrying the page the person wanted (SCRUM-62 AC7, SCRUM-68 AC6).
"""

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.sessions import COOKIE_NAMES, resolve_session, set_session_cookie
from app.db import get_db
from app.models import AuthScope, User

NOT_SIGNED_IN = {"code": "not_signed_in", "message": "Please sign in to continue."}


def resolve_user(
    request: Request, response: Response, db: Session, scope: AuthScope
) -> User | None:
    """The signed-in user for this scope's cookie, refreshing the cookie on `response`, or
    None. The one set of session rules, used by Identity's own routes (below) and by the
    gateway's introspection (`routers/internal.py`)."""
    token = request.cookies.get(COOKIE_NAMES[scope])
    auth_session = resolve_session(db, token, scope)
    # Removing an administrator ends their sessions; this also covers one that slipped
    # through while the removal was being saved (SCRUM-81).
    if auth_session is None or auth_session.user.is_removed:
        return None
    # Only the admin cookie counts for the portal, and only for a current administrator
    # (SCRUM-68 AC6, SCRUM-81 AC4).
    if scope == AuthScope.ADMIN and not auth_session.user.is_admin:
        return None
    set_session_cookie(response, scope, token)
    return auth_session.user


def _current_user(request: Request, response: Response, db: Session, scope: AuthScope) -> User:
    user = resolve_user(request, response, db, scope)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_SIGNED_IN)
    return user


def require_user(request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    """Any signed-in main-app user."""
    return _current_user(request, response, db, AuthScope.APP)


def require_admin(request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    """A signed-in administrator on the admin portal.

    Only the admin cookie counts. Being signed in to the main app, even as an
    administrator, does not open admin routes (SCRUM-68 AC6). If someone is removed as an
    administrator while signed in, they are refused from their next request (SCRUM-81 AC4).
    """
    return _current_user(request, response, db, AuthScope.ADMIN)
