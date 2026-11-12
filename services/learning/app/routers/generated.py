"""AI-generated lessons (docs/ai-lessons-api.md, "Learning"). The rules live in
app/generated.py.

Everything is the signed-in learner's own: another user's request or attempt is answered as
missing. Playing mirrors app/routers/lessons.py and never touches lesson attempts,
completions or progress.
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import generated
from app.db import get_db
from app.platform.principal import Principal, require_principal
from app.schemas import (
    AnswerRequest,
    CheckResultOut,
    GeneratedAttemptOut,
    GeneratedAttemptResultOut,
    GeneratedListItemOut,
    GeneratedReportOut,
    GeneratedReportRequest,
    GeneratedStatusOut,
    GenerateOptionsOut,
    GenerateRequest,
    LearnerLessonOut,
    RatingRequest,
)

signed_in = require_principal("app")
router = APIRouter(dependencies=[Depends(signed_in)])

NOT_FOUND = {404: {"description": "No such generated lesson of yours (generated_not_found)"}}
ATTEMPT_NOT_FOUND = {404: {"description": "No such attempt of yours (attempt_not_found)"}}


@router.get("/generate/options", response_model=GenerateOptionsOut)
def get_options(user: Principal = Depends(signed_in), db: Session = Depends(get_db)):
    """What the Practice and Generate pages need: topics, mistakes, levels, the limit."""
    return generated.options(db, user.user_id)


@router.post(
    "/generate",
    response_model=GeneratedStatusOut,
    status_code=202,
    responses={
        404: {"description": "No lesson learners can open in the topic (topic_not_found)"},
        409: {"description": "Focus mistakes with none in the topic (no_mistakes)"},
        429: {"description": "The daily limit is used up (daily_limit_reached)"},
    },
)
def request_lesson(
    body: GenerateRequest, user: Principal = Depends(signed_in), db: Session = Depends(get_db)
):
    """Ask for a lesson; it is written in the background."""
    row = generated.request(
        db,
        user.user_id,
        topic_id=body.topic_id,
        focus=body.focus,
        ask=body.ask or None,
        difficulty=body.difficulty,
        length=body.length,
    )
    return generated.status_out(db, row)


@router.get("/generate/{generated_id}", response_model=GeneratedStatusOut, responses=NOT_FOUND)
def get_status(
    generated_id: uuid.UUID, user: Principal = Depends(signed_in), db: Session = Depends(get_db)
):
    return generated.status(db, user.user_id, generated_id)


@router.post(
    "/generate/{generated_id}/cancel", response_model=GeneratedStatusOut, responses=NOT_FOUND
)
def cancel(
    generated_id: uuid.UUID, user: Principal = Depends(signed_in), db: Session = Depends(get_db)
):
    """Cancel a waiting request (refunded). A finished one is returned unchanged."""
    return generated.cancel(db, user.user_id, generated_id)


@router.get("/generated", response_model=list[GeneratedListItemOut])
def list_generated(user: Principal = Depends(signed_in), db: Session = Depends(get_db)):
    """The learner's generated lessons, newest first, without failed or cancelled ones."""
    return generated.listed(db, user.user_id)


@router.get(
    "/generated/{generated_id}/lesson", response_model=LearnerLessonOut, responses=NOT_FOUND
)
def get_lesson(
    generated_id: uuid.UUID, user: Principal = Depends(signed_in), db: Session = Depends(get_db)
):
    """The ready lesson as a deck, without which options are right."""
    return generated.learner_lesson(db, user.user_id, generated_id)


@router.post(
    "/generated/{generated_id}/attempts",
    response_model=GeneratedAttemptOut,
    status_code=201,
    responses=NOT_FOUND,
)
def start_attempt(
    generated_id: uuid.UUID, user: Principal = Depends(signed_in), db: Session = Depends(get_db)
):
    return generated.start_attempt(db, user.user_id, generated_id)


@router.post(
    "/generated/attempts/{attempt_id}/answers",
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
):
    """Check an answer on the server. Only the first answer to a question counts."""
    return generated.answer(db, user.user_id, attempt_id, body.question_id, body.option_id)


@router.post(
    "/generated/attempts/{attempt_id}/finish",
    response_model=GeneratedAttemptResultOut,
    responses={
        **ATTEMPT_NOT_FOUND,
        409: {"description": "A question is unanswered (questions_unanswered)"},
    },
)
def finish(
    attempt_id: uuid.UUID, user: Principal = Depends(signed_in), db: Session = Depends(get_db)
):
    """Finish the attempt and keep the best score. Finishing again changes nothing."""
    return generated.finish(db, user.user_id, attempt_id)


@router.post("/generated/{generated_id}/rating", status_code=204, responses=NOT_FOUND)
def rate(
    generated_id: uuid.UUID,
    body: RatingRequest,
    user: Principal = Depends(signed_in),
    db: Session = Depends(get_db),
) -> Response:
    """Was it useful? Saving again replaces the rating."""
    generated.rate(db, user.user_id, generated_id, body.useful, list(body.reasons))
    return Response(status_code=204)


@router.post(
    "/generated/{generated_id}/reports",
    response_model=GeneratedReportOut,
    status_code=201,
    responses={**NOT_FOUND, 422: {"description": "Not a card of this lesson (card_not_found)"}},
)
def report(
    generated_id: uuid.UUID,
    body: GeneratedReportRequest,
    user: Principal = Depends(signed_in),
    db: Session = Depends(get_db),
):
    """Flag a problem on one card. Stored here; there is no admin screen yet."""
    return generated.report(db, user.user_id, generated_id, body.card_id, body.reason, body.note)
