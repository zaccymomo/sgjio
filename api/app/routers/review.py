"""The signed-in user's mistakes to review (SCRUM-44). The rules live in app/review.py.

There is no user id in the path, so one user can never read another's answers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.db import get_db
from app.models import User
from app.review import mistakes_for
from app.schemas import MistakeOut, ReviewOut

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/review", response_model=ReviewOut)
def get_review(user: User = Depends(require_user), db: Session = Depends(get_db)) -> ReviewOut:
    """The questions whose latest answer was wrong, newest first, each with its right answer
    and explanation as the lesson reads now."""
    return ReviewOut(mistakes=[MistakeOut.model_validate(m) for m in mistakes_for(db, user.id)])
