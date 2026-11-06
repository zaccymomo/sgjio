"""Who is making the request, as the gateway says (contracts/README.md, "Auth contract").

The gateway asks Identity about the session cookie on every protected request, then sets
X-User-Id, X-User-Scope, X-User-Role, X-User-Type and X-Profile-Completed, plus
X-Gateway-Key. A request without the right key did not come through the gateway, so its
X-User-* headers mean nothing and it is refused.

    @router.get("/progress")
    def progress(principal: Principal = Depends(require_principal("app"))): ...
"""

import hmac
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from .config import get_config
from .errors import not_signed_in

Scope = Literal["app", "admin"]


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    scope: Scope
    role: str  # "user" or "admin"
    user_type: str | None  # "newcomer" or "singaporean"; None for administrators
    profile_completed: bool


def came_through_gateway(request: Request) -> bool:
    expected = get_config().gateway_key
    given = request.headers.get("x-gateway-key", "")
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


def principal_from_headers(request: Request, scope: Scope) -> Principal | None:
    headers = request.headers
    if not came_through_gateway(request) or headers.get("x-user-scope") != scope:
        return None
    role = headers.get("x-user-role", "")
    if role not in ("user", "admin") or (scope == "admin" and role != "admin"):
        return None
    try:
        user_id = uuid.UUID(headers.get("x-user-id", ""))
    except ValueError:
        return None
    return Principal(
        user_id=user_id,
        scope=scope,
        role=role,
        user_type=headers.get("x-user-type") or None,
        profile_completed=headers.get("x-profile-completed", "").lower() == "true",
    )


def require_principal(scope: Scope) -> Callable[[Request], Principal]:
    """A FastAPI dependency: the signed-in principal for `scope`, or 401 not_signed_in."""

    def dependency(request: Request) -> Principal:
        principal = principal_from_headers(request, scope)
        if principal is None:
            raise not_signed_in()
        return principal

    dependency.__name__ = f"require_{scope}_principal"
    return dependency
