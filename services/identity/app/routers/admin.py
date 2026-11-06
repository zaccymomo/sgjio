"""Identity's admin-only routes: the Administrators page (SCRUM-81) and the ping check.

Every route here depends on require_admin, through the router, so a route added below is
protected even if its author forgets the guard. Content's and Learning's admin routes live
in those services; the gateway routes /api/admin/admins* and /api/admin/ping here.

Refusals from app.admins are platform `Problem`s, answered by the error handler with the
same {"detail": {"code", "message", ...extra, "field"?}} body the monolith sent.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import admins
from app.auth.deps import require_admin
from app.db import get_db
from app.models import User
from app.schemas import AdminInviteRequest, AdminOut, AdminsOut

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/ping")
def admin_ping(admin: User = Depends(require_admin)) -> dict:
    """A trivial protected route, for checking the admin guard end to end."""
    return {"ok": True, "admin": admin.email}


# --- Administrators (SCRUM-81) ------------------------------------------------------------

ADMIN_NOT_FOUND = {404: {"description": "No administrator with that id (admin_not_found)"}}


@router.get("/admins", response_model=AdminsOut)
def list_admins(
    admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminsPage:
    """Every administrator with their last sign-in, removed ones apart, and the latest
    changes (AC1)."""
    return admins.list_admins(db, admin)


@router.post(
    "/admins",
    response_model=AdminOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "description": "The email has an account: email_in_use (a learner's, AC3), "
            "already_admin, already_invited or admin_removed (these carry admin_id)"
        },
        422: {"description": "outside_domain until allow_other_domain is set, or a bad field"},
    },
)
def invite_admin(
    body: AdminInviteRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminSummary:
    """Create an administrator and email them a link to choose a password (AC2)."""
    invited = admins.invite_admin(db, admin, body.name, body.email, body.allow_other_domain)
    return admins.get_summary(db, admin, invited.id)


@router.post(
    "/admins/{admin_id}/resend-invite",
    response_model=AdminOut,
    responses={**ADMIN_NOT_FOUND, 409: {"description": "Not waiting for an invite (not_invited)"}},
)
def resend_invite(
    admin_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminSummary:
    """Email a new invite link. The earlier one stops working."""
    admins.resend_invite(db, admin, admin_id)
    return admins.get_summary(db, admin, admin_id)


@router.post(
    "/admins/{admin_id}/remove",
    response_model=AdminOut,
    responses={
        **ADMIN_NOT_FOUND,
        409: {"description": "Yourself (cannot_remove_self) or the last one (last_admin)"},
    },
)
def remove_admin(
    admin_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminSummary:
    """Close an administrator's account, or cancel their invite: their sessions end and
    they can no longer sign in (AC4, AC5). Safe to repeat."""
    admins.remove_admin(db, admin, admin_id)
    return admins.get_summary(db, admin, admin_id)


@router.post("/admins/{admin_id}/restore", response_model=AdminOut, responses=ADMIN_NOT_FOUND)
def restore_admin(
    admin_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminSummary:
    """Give a removed administrator access again, with a new link to choose a password.
    Safe to repeat."""
    admins.restore_admin(db, admin, admin_id)
    return admins.get_summary(db, admin, admin_id)
