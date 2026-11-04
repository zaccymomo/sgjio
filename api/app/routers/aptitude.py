"""Signed-in Newcomer aptitude quiz routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import aptitude
from app.auth.deps import require_user
from app.db import get_db
from app.models import User
from app.schemas import AptitudeQuizOut, AptitudeResultOut, AptitudeSubmitIn

router = APIRouter(dependencies=[Depends(require_user)])


def _call(action):
    try:
        return action()
    except aptitude.AptitudeError as error:
        raise HTTPException(
            error.status_code, {"code": error.code, "message": error.message}
        ) from None


@router.post("/aptitude/start", response_model=AptitudeQuizOut)
def start(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return {"questions": _call(lambda: aptitude.start_quiz(db, user))}


@router.post("/aptitude/submit", response_model=AptitudeResultOut)
def submit(
    body: AptitudeSubmitIn, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    return aptitude.result_out(_call(lambda: aptitude.submit_quiz(db, user, body.answers)))


@router.post("/aptitude/skip", status_code=status.HTTP_204_NO_CONTENT)
def skip(user: User = Depends(require_user), db: Session = Depends(get_db)) -> None:
    _call(lambda: aptitude.skip_quiz(db, user))


@router.get("/aptitude/latest", response_model=AptitudeResultOut)
def latest(user: User = Depends(require_user), db: Session = Depends(get_db)):
    attempt = aptitude.latest_attempt(db, user.id)
    if attempt is None:
        raise HTTPException(
            404, {"code": "attempt_not_found", "message": "No aptitude result yet."}
        )
    return aptitude.result_out(attempt)
