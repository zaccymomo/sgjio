"""Admin-only routes. Every route here must depend on require_admin.

Setting `dependencies` on the router means a new route added below is protected even if
its author forgets to add the guard.
"""

from fastapi import APIRouter, Depends

from app.auth.deps import require_admin
from app.models import User

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/ping")
def admin_ping(admin: User = Depends(require_admin)) -> dict:
    """A trivial protected route, for checking the admin guard end to end."""
    return {"ok": True, "admin": admin.email}
