"""Signed-in Newcomer routes for the adaptive per-topic aptitude quiz."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import aptitude
from app.auth.deps import require_user
from app.db import get_db
from app.models import User
from app.schemas import AptitudeNextIn, AptitudeResultOut, AptitudeStepOut, AptitudeSubmitIn

router = APIRouter(dependencies=[Depends(require_user)])


def _call(action):
    try:
        return action()
    except aptitude.AptitudeError as error:
        raise HTTPException(
            error.status_code, detail={"code": error.code, "message": error.message}
        ) from None


@router.post("/aptitude/start", response_model=AptitudeStepOut)
def start(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return _call(lambda: aptitude.start_quiz(db, user))


@router.post("/aptitude/next", response_model=AptitudeStepOut)
def next_step(
    body: AptitudeNextIn,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _call(lambda: aptitude.next_question(db, user, body.answers))


@router.post("/aptitude/submit", response_model=AptitudeResultOut)
def submit(
    body: AptitudeSubmitIn,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    attempt = _call(lambda: aptitude.submit_quiz(db, user, body.answers))
    return aptitude.result_out(db, attempt)


@router.get("/aptitude/result", response_model=AptitudeResultOut)
def result(user: User = Depends(require_user), db: Session = Depends(get_db)):
    attempt = aptitude.quiz_attempt(db, user.id)
    if attempt is None:
        raise HTTPException(
            404, detail={"code": "attempt_not_found", "message": "No aptitude result yet."}
        )
    return aptitude.result_out(db, attempt)
