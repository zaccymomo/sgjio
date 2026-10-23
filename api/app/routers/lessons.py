"""Learners' lessons: reading one and answering its questions (SCRUM-15, SCRUM-16), and
reporting a problem on a card (SCRUM-82).

Everything here is the signed-in user's own: attempts are found by id and owner together,
so one user can never answer or read another's. The rules live in app/learning.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import learning, reports
from app.auth.deps import require_user
from app.db import get_db
from app.models import User
from app.problems import ContentProblem
from app.schemas import (
    AnswerRequest,
    AttemptOut,
    AttemptResultOut,
    AttemptStartRequest,
    CheckResultOut,
    LearnerLessonOut,
    ReportRequest,
    ReportSentOut,
)

router = APIRouter(dependencies=[Depends(require_user)])

UNAVAILABLE = {404: {"description": "Not published, or no such lesson (lesson_unavailable)"}}
ATTEMPT_NOT_FOUND = {404: {"description": "No such attempt of yours (attempt_not_found)"}}


def _refuse(problem: ContentProblem) -> HTTPException:
    detail = {"code": problem.code, "message": problem.message, **problem.extra}
    if problem.field:
        detail["field"] = problem.field
    return HTTPException(problem.status_code, detail=detail)


@router.get("/lessons/{lesson_id}", response_model=LearnerLessonOut, responses=UNAVAILABLE)
def get_lesson(lesson_id: uuid.UUID, db: Session = Depends(get_db)) -> learning.LearnerLesson:
    """The lesson's latest version, without which options are right (SCRUM-15 AC1)."""
    try:
        return learning.learner_lesson(db, lesson_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None


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
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Start a run through the lesson, at the version the learner was shown."""
    try:
        return learning.start_attempt(db, user.id, lesson_id, body.version)
    except ContentProblem as problem:
        raise _refuse(problem) from None


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
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> learning.CheckResult:
    """Check an answer on the server (SCRUM-16 AC1). Only the first answer to a question
    counts; sending it again returns the same result and records nothing (AC6)."""
    try:
        return learning.answer(db, user.id, attempt_id, body.question_id, body.option_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.post(
    "/attempts/{attempt_id}/finish",
    response_model=AttemptResultOut,
    responses={
        **ATTEMPT_NOT_FOUND,
        409: {"description": "A question is unanswered (questions_unanswered)"},
    },
)
def finish(
    attempt_id: uuid.UUID, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> learning.AttemptResult:
    """Finish the attempt: the lesson is completed, right or wrong, and the best score is
    kept (SCRUM-16 AC3 to AC6). Finishing again changes nothing."""
    try:
        return learning.finish(db, user.id, attempt_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.post(
    "/lessons/{lesson_id}/reports",
    response_model=ReportSentOut,
    status_code=201,
    responses={**UNAVAILABLE, 422: {"description": "Not a version or card of this lesson"}},
)
def report_problem(
    lesson_id: uuid.UUID,
    body: ReportRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Report a problem on one card, naming the version shown (SCRUM-82)."""
    try:
        return reports.report_problem(
            db, user.id, lesson_id, body.version, body.card_id, body.reason, body.note
        )
    except ContentProblem as problem:
        raise _refuse(problem) from None
