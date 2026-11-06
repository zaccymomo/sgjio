"""Session introspection for the gateway (contracts/README.md, "Auth contract").

For every protected Content or Learning route, nginx asks here, without the request body:

    GET /internal/auth/app      reads sgjio_session
    GET /internal/auth/admin    reads sgjio_admin_session

and Identity runs exactly the checks its own routes run (`app.auth.deps`): the session
exists for that scope and has not expired, its sliding expiry moves forward (at most once
a minute), the account has not been removed, and, for admin, it is an administrator.

- 200, empty body, with X-User-Id, X-User-Scope, X-User-Role, X-User-Type (empty for an
  account with none, i.e. administrators), X-Profile-Completed and the refreshed session
  cookie, re-sent on every signed-in request as the monolith did. nginx copies the X-User-*
  headers onto the proxied request and the Set-Cookie onto the browser's response.
- 401, empty body, otherwise. nginx answers the browser with the usual not_signed_in body.

Only the gateway may ask: a request without the shared X-Gateway-Key gets 401. The gateway
never routes /internal/*, so browsers cannot reach this at all.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.deps import resolve_user
from app.db import get_db
from app.models import AuthScope
from app.platform.principal import came_through_gateway

router = APIRouter(prefix="/internal/auth", tags=["Internal"], include_in_schema=False)


def _introspect(request: Request, db: Session, scope: AuthScope) -> Response:
    headers = {"Cache-Control": "no-store"}
    if not came_through_gateway(request):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED, headers=headers)
    response = Response(status_code=status.HTTP_200_OK, headers=headers)
    user = resolve_user(request, response, db, scope)
    if user is None:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED, headers=headers)
    response.headers["X-User-Id"] = str(user.id)
    response.headers["X-User-Scope"] = scope.value
    response.headers["X-User-Role"] = user.role.value
    response.headers["X-User-Type"] = user.user_type.value if user.user_type else ""
    response.headers["X-Profile-Completed"] = "true" if user.profile is not None else "false"
    return response


@router.get("/app")
def introspect_app(request: Request, db: Session = Depends(get_db)) -> Response:
    return _introspect(request, db, AuthScope.APP)


@router.get("/admin")
def introspect_admin(request: Request, db: Session = Depends(get_db)) -> Response:
    return _introspect(request, db, AuthScope.ADMIN)
