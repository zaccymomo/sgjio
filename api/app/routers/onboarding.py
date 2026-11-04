"""The introduction a new user sees on first sign-in (SCRUM-94).

The main app shows the introduction while `users.intro_finished_at` is empty. Finishing
and skipping it are the same here: either way it is not shown automatically again (AC6).
There is no user id in the path, so users only ever mark their own.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.db import get_db
from app.models import User
from app.schemas import UserOut

router = APIRouter(dependencies=[Depends(require_user)])


@router.post("/intro/finished", response_model=UserOut)
def finish_intro(user: User = Depends(require_user), db: Session = Depends(get_db)) -> User:
    """Record that the introduction was finished or skipped. Repeating it keeps the first time.

    Returns the user, as /auth/me would, so the app can carry on without asking again."""
    if user.intro_finished_at is None:
        user.intro_finished_at = datetime.now(UTC)
        db.commit()
    return user
