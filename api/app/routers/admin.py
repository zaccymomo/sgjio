"""Admin-only routes. Every route here must depend on require_admin.

Setting `dependencies` on the router means a new route added below is protected even if
its author forgets to add the guard.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app import lessons, topics
from app.auth.deps import require_admin
from app.db import get_db
from app.models import User
from app.problems import ContentProblem
from app.schemas import (
    LessonCreateRequest,
    LessonOrderRequest,
    LessonOut,
    LessonSummaryOut,
    LessonUpdateRequest,
    TopicOrderRequest,
    TopicOut,
    TopicRequest,
)

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/ping")
def admin_ping(admin: User = Depends(require_admin)) -> dict:
    """A trivial protected route, for checking the admin guard end to end."""
    return {"ok": True, "admin": admin.email}


# --- Topics (SCRUM-57) --------------------------------------------------------------------

NOT_FOUND = {404: {"description": "No topic with that id (topic_not_found)"}}
NAME_TAKEN = {409: {"description": "Another topic has that name (topic_name_taken)"}}
OUT_OF_DATE = {409: {"description": "The page's list is out of date (order_out_of_date)"}}


def _refuse(problem: ContentProblem) -> HTTPException:
    detail = {"code": problem.code, "message": problem.message}
    if problem.field:
        detail["field"] = problem.field
    return HTTPException(problem.status_code, detail=detail)


@router.get("/topics", response_model=list[TopicOut])
def list_topics(db: Session = Depends(get_db)) -> list[topics.TopicSummary]:
    """Every topic, archived ones included, with lesson counts."""
    return topics.list_topics(db)


# Declared before the /topics/{topic_id} routes, so "order" is never read as a topic id.
@router.put("/topics/order", response_model=list[TopicOut], responses=OUT_OF_DATE)
def reorder_topics(
    body: TopicOrderRequest, db: Session = Depends(get_db)
) -> list[topics.TopicSummary]:
    """Set the order of the active topics (SCRUM-66), which is also the order of users'
    circles. List every active topic exactly once, plus the order the page showed; a
    page that was out of date gets 409 order_out_of_date. Returns every topic, in order."""
    try:
        return topics.reorder_topics(db, body.ids, body.previous_ids)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.post(
    "/topics",
    response_model=TopicOut,
    status_code=status.HTTP_201_CREATED,
    responses=NAME_TAKEN,
)
def create_topic(body: TopicRequest, db: Session = Depends(get_db)) -> topics.TopicSummary:
    try:
        return topics.create_topic(db, body.name)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.patch("/topics/{topic_id}", response_model=TopicOut, responses={**NOT_FOUND, **NAME_TAKEN})
def rename_topic(
    topic_id: uuid.UUID, body: TopicRequest, db: Session = Depends(get_db)
) -> topics.TopicSummary:
    try:
        return topics.rename_topic(db, topic_id, body.name)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.post("/topics/{topic_id}/archive", response_model=TopicOut, responses=NOT_FOUND)
def archive_topic(topic_id: uuid.UUID, db: Session = Depends(get_db)) -> topics.TopicSummary:
    """Hide the topic from users, keeping its lessons and progress. Safe to repeat."""
    try:
        return topics.archive_topic(db, topic_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.post("/topics/{topic_id}/restore", response_model=TopicOut, responses=NOT_FOUND)
def restore_topic(topic_id: uuid.UUID, db: Session = Depends(get_db)) -> topics.TopicSummary:
    """Show an archived topic to users again. Safe to repeat."""
    try:
        return topics.restore_topic(db, topic_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.delete(
    "/topics/{topic_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **NOT_FOUND,
        409: {"description": "The topic has lessons; archive it instead (topic_not_empty)"},
    },
)
def delete_topic(topic_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    try:
        topics.delete_topic(db, topic_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None


# --- Lessons (SCRUM-66) -------------------------------------------------------------------


@router.get("/lessons", response_model=list[LessonSummaryOut])
def list_lessons(db: Session = Depends(get_db)) -> list[lessons.LessonSummary]:
    """Every lesson of every status, without its body, in topic order then lesson order.
    Lessons with no topic come last."""
    return lessons.list_lessons(db)


@router.put(
    "/lessons/order",
    response_model=list[LessonSummaryOut],
    responses={**NOT_FOUND, **OUT_OF_DATE},
)
def reorder_lessons(
    body: LessonOrderRequest, db: Session = Depends(get_db)
) -> list[lessons.LessonSummary]:
    """Set the order of one topic's lessons, or of those with no topic (`topic_id: null`).
    List every lesson in that group exactly once, plus the order the page showed; a page
    that was out of date gets 409 order_out_of_date. Returns every lesson, in order."""
    try:
        return lessons.reorder_lessons(db, body.topic_id, body.ids, body.previous_ids)
    except ContentProblem as problem:
        raise _refuse(problem) from None


# --- Lesson drafts (SCRUM-64) -------------------------------------------------------------

LESSON_NOT_FOUND = {404: {"description": "No lesson with that id (lesson_not_found)"}}
TOPIC_REFUSED = {
    404: {"description": "No topic with that id (topic_not_found, field topic_id)"},
    409: {"description": "That topic is archived (topic_archived, field topic_id)"},
}


@router.post(
    "/lessons",
    response_model=LessonOut,
    status_code=status.HTTP_201_CREATED,
    responses=TOPIC_REFUSED,
)
def create_lesson(body: LessonCreateRequest, db: Session = Depends(get_db)) -> lessons.LessonDetail:
    """Create a draft at the end of its topic. Every field may be empty."""
    try:
        return lessons.create_lesson(db, body.title, body.content, body.topic_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.get("/lessons/{lesson_id}", response_model=LessonOut, responses=LESSON_NOT_FOUND)
def get_lesson(lesson_id: uuid.UUID, db: Session = Depends(get_db)) -> lessons.LessonDetail:
    """One lesson of any status, body included."""
    try:
        return lessons.get_lesson(db, lesson_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.patch(
    "/lessons/{lesson_id}",
    response_model=LessonOut,
    responses={
        **LESSON_NOT_FOUND,
        **TOPIC_REFUSED,
        409: {
            "description": "Not a draft (lesson_not_draft), changed since it was loaded "
            "(lesson_out_of_date), or the topic is archived (topic_archived)"
        },
    },
)
def update_lesson(
    lesson_id: uuid.UUID, body: LessonUpdateRequest, db: Session = Depends(get_db)
) -> lessons.LessonDetail:
    """Change a draft's title, content or topic; fields left out are kept. A new topic puts
    the lesson at the end of it. Send the `updated_at` the editor loaded."""
    try:
        return lessons.update_lesson(db, lesson_id, body.updated_at, body.changes())
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.delete(
    "/lessons/{lesson_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **LESSON_NOT_FOUND,
        409: {
            "description": "Published at some point, so withdraw it instead "
            "(lesson_not_deletable), or changed since it was loaded (lesson_out_of_date)"
        },
    },
)
def delete_lesson(
    lesson_id: uuid.UUID,
    updated_at: AwareDatetime = Query(description="The `updated_at` the editor loaded"),
    db: Session = Depends(get_db),
) -> None:
    """Delete a lesson that has never been published."""
    try:
        lessons.delete_lesson(db, lesson_id, updated_at)
    except ContentProblem as problem:
        raise _refuse(problem) from None
