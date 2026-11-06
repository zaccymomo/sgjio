"""Learners' lessons: reading one and answering its questions (SCRUM-15, SCRUM-16).

Everything here is the signed-in user's own: attempts are found by id and owner together,
so one user can never answer or read another's. The rules live in app/learning.py.
Reporting a problem on a card (POST /api/lessons/{id}/reports) belongs to Content.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import learning
from app.db import get_db
from app.platform.principal import Principal, require_principal
from app.schemas import (
    AnswerRequest,
    AttemptOut,
    AttemptResultOut,
    AttemptStartRequest,
    CheckResultOut,
    LearnerLessonOut,
)

signed_in = require_principal("app")
router = APIRouter(dependencies=[Depends(signed_in)])

UNAVAILABLE = {404: {"description": "Not published, or no such lesson (lesson_unavailable)"}}
ATTEMPT_NOT_FOUND = {404: {"description": "No such attempt of yours (attempt_not_found)"}}


@router.get("/lessons/{lesson_id}", response_model=LearnerLessonOut, responses=UNAVAILABLE)
def get_lesson(lesson_id: uuid.UUID, db: Session = Depends(get_db)) -> learning.LearnerLesson:
    """The lesson's latest version, without which options are right (SCRUM-15 AC1)."""
    return learning.learner_lesson(db, lesson_id)


@router.post(
    "/lessons/{lesson_id}/attempts",
    response_model=AttemptOut,
    status_code=201,
    responses={
        **UNAVAILABLE,
        409: {"description": "A newer version has been published (lesson_updated)"},
    },
)
def start_attempt(
    lesson_id: uuid.UUID,
    body: AttemptStartRequest,
    user: Principal = Depends(signed_in),
    db: Session = Depends(get_db),
):
    """Start a run through the lesson, at the version the learner was shown."""
    return learning.start_attempt(db, user.user_id, lesson_id, body.version)


@router.post(
    "/attempts/{attempt_id}/answers",
    response_model=CheckResultOut,
    responses={
        **ATTEMPT_NOT_FOUND,
        409: {"description": "The attempt is finished (attempt_finished)"},
        422: {"description": "Not a question or option of this lesson"},
    },
)
def answer(
    attempt_id: uuid.UUID,
    body: AnswerRequest,
    user: Principal = Depends(signed_in),
    db: Session = Depends(get_db),
) -> learning.CheckResult:
    """Check an answer on the server (SCRUM-16 AC1). Only the first answer to a question
    counts; sending it again returns the same result and records nothing (AC6)."""
    return learning.answer(db, user.user_id, attempt_id, body.question_id, body.option_id)


@router.post(
    "/attempts/{attempt_id}/finish",
    response_model=AttemptResultOut,
    responses={
        **ATTEMPT_NOT_FOUND,
        409: {"description": "A question is unanswered (questions_unanswered)"},
    },
)
def finish(
    attempt_id: uuid.UUID, user: Principal = Depends(signed_in), db: Session = Depends(get_db)
) -> learning.AttemptResult:
    """Finish the attempt: the lesson is completed, right or wrong, and the best score is
    kept (SCRUM-16 AC3 to AC6). Finishing again changes nothing."""
    return learning.finish(db, user.user_id, attempt_id)
