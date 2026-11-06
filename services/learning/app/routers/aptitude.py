"""Signed-in Newcomer routes for the adaptive per-topic aptitude quiz. Who may take it comes
from the caller's principal (X-User-Type, X-Profile-Completed), which the gateway asks
Identity for on every request."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import aptitude
from app.db import get_db
from app.platform.errors import Problem
from app.platform.principal import Principal, require_principal
from app.schemas import AptitudeNextIn, AptitudeResultOut, AptitudeStepOut, AptitudeSubmitIn

signed_in = require_principal("app")
router = APIRouter(dependencies=[Depends(signed_in)])


@router.post("/aptitude/start", response_model=AptitudeStepOut)
def start(user: Principal = Depends(signed_in), db: Session = Depends(get_db)):
    return aptitude.start_quiz(db, user)


@router.post("/aptitude/next", response_model=AptitudeStepOut)
def next_step(
    body: AptitudeNextIn,
    user: Principal = Depends(signed_in),
    db: Session = Depends(get_db),
):
    return aptitude.next_question(db, user, body.answers)


@router.post("/aptitude/submit", response_model=AptitudeResultOut)
def submit(
    body: AptitudeSubmitIn,
    user: Principal = Depends(signed_in),
    db: Session = Depends(get_db),
):
    attempt = aptitude.submit_quiz(db, user, body.answers)
    return aptitude.result_out(db, attempt)


@router.post("/aptitude/skip", status_code=status.HTTP_204_NO_CONTENT)
def skip(user: Principal = Depends(signed_in), db: Session = Depends(get_db)) -> None:
    aptitude.skip_quiz(db, user)


@router.get("/aptitude/result", response_model=AptitudeResultOut)
def result(user: Principal = Depends(signed_in), db: Session = Depends(get_db)):
    attempt = aptitude.quiz_attempt(db, user.user_id)
    if attempt is None:
        raise Problem("attempt_not_found", "No aptitude result yet.", 404)
    return aptitude.result_out(db, attempt)
