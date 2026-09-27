"""Progress for the signed-in user, read by the landing page circles (SCRUM-43).

Setting `dependencies` on the router means a route added below is signed-in-only even if
its author forgets the guard. Progress is always the caller's own: there is no user id in
the path, so one user can never read another's figures.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.db import get_db
from app.models import User
from app.progress import progress_for
from app.schemas import ProgressOut

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/progress", response_model=ProgressOut)
def get_progress(user: User = Depends(require_user), db: Session = Depends(get_db)) -> ProgressOut:
    """Lessons completed out of lessons available, per topic and overall."""
    return ProgressOut.model_validate(progress_for(db, user.id))
