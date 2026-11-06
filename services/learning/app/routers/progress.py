"""Progress for the signed-in user: the landing page circles (SCRUM-43), the lessons
behind each one (SCRUM-53), and searching every topic's lessons (SCRUM-85).

Setting `dependencies` on the router means a route added below is signed-in-only even if
its author forgets the guard. Progress is always the caller's own: there is no user id in
the path, so one user can never read another's figures.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.platform.principal import Principal, require_principal
from app.progress import (
    SearchResult,
    TopicLessons,
    progress_for,
    search_lessons,
    topic_lessons,
)
from app.schemas import LessonSearchResultOut, ProgressOut, TopicLessonsOut

signed_in = require_principal("app")
router = APIRouter(dependencies=[Depends(signed_in)])


@router.get("/progress", response_model=ProgressOut)
def get_progress(
    user: Principal = Depends(signed_in), db: Session = Depends(get_db)
) -> ProgressOut:
    """Lessons completed out of lessons available, per topic and overall, and the suggested
    next lesson (SCRUM-6)."""
    return ProgressOut.model_validate(progress_for(db, user.user_id))


@router.get(
    "/topics/{topic_id}",
    response_model=TopicLessonsOut,
    responses={404: {"description": "Archived, or no such topic (topic_unavailable)"}},
)
def get_topic(
    topic_id: uuid.UUID, user: Principal = Depends(signed_in), db: Session = Depends(get_db)
) -> TopicLessons:
    """A topic's published lessons in order, each marked completed or not (SCRUM-53)."""
    return topic_lessons(db, user.user_id, topic_id)


@router.get("/search", response_model=list[LessonSearchResultOut])
def search(
    q: str = Query(min_length=2, max_length=100, description="A word or phrase, e.g. chope"),
    user: Principal = Depends(signed_in),
    db: Session = Depends(get_db),
) -> list[SearchResult]:
    """Published lessons in every topic whose title or card text contains `q`, each marked
    completed or not (SCRUM-85)."""
    return search_lessons(db, user.user_id, q)
