"""Admin-only routes. Every route here must depend on require_admin.

Setting `dependencies` on the router means a new route added below is protected even if
its author forgets to add the guard.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import topics
from app.auth.deps import require_admin
from app.db import get_db
from app.models import User
from app.schemas import TopicOut, TopicRequest

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/ping")
def admin_ping(admin: User = Depends(require_admin)) -> dict:
    """A trivial protected route, for checking the admin guard end to end."""
    return {"ok": True, "admin": admin.email}


# --- Topics (SCRUM-57) --------------------------------------------------------------------

NOT_FOUND = {404: {"description": "No topic with that id (topic_not_found)"}}
NAME_TAKEN = {409: {"description": "Another topic has that name (topic_name_taken)"}}


def _refuse(problem: topics.TopicProblem) -> HTTPException:
    detail = {"code": problem.code, "message": problem.message}
    if problem.field:
        detail["field"] = problem.field
    return HTTPException(problem.status_code, detail=detail)


@router.get("/topics", response_model=list[TopicOut])
def list_topics(db: Session = Depends(get_db)) -> list[topics.TopicSummary]:
    """Every topic, archived ones included, with lesson counts."""
    return topics.list_topics(db)


@router.post(
    "/topics",
    response_model=TopicOut,
    status_code=status.HTTP_201_CREATED,
    responses=NAME_TAKEN,
)
def create_topic(body: TopicRequest, db: Session = Depends(get_db)) -> topics.TopicSummary:
    try:
        return topics.create_topic(db, body.name)
    except topics.TopicProblem as problem:
        raise _refuse(problem) from None


@router.patch("/topics/{topic_id}", response_model=TopicOut, responses={**NOT_FOUND, **NAME_TAKEN})
def rename_topic(
    topic_id: uuid.UUID, body: TopicRequest, db: Session = Depends(get_db)
) -> topics.TopicSummary:
    try:
        return topics.rename_topic(db, topic_id, body.name)
    except topics.TopicProblem as problem:
        raise _refuse(problem) from None


@router.post("/topics/{topic_id}/archive", response_model=TopicOut, responses=NOT_FOUND)
def archive_topic(topic_id: uuid.UUID, db: Session = Depends(get_db)) -> topics.TopicSummary:
    """Hide the topic from users, keeping its lessons and progress. Safe to repeat."""
    try:
        return topics.archive_topic(db, topic_id)
    except topics.TopicProblem as problem:
        raise _refuse(problem) from None


@router.post("/topics/{topic_id}/restore", response_model=TopicOut, responses=NOT_FOUND)
def restore_topic(topic_id: uuid.UUID, db: Session = Depends(get_db)) -> topics.TopicSummary:
    """Show an archived topic to users again. Safe to repeat."""
    try:
        return topics.restore_topic(db, topic_id)
    except topics.TopicProblem as problem:
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
    except topics.TopicProblem as problem:
        raise _refuse(problem) from None
