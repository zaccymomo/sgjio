"""Lesson insights for administrators (SCRUM-84): the one admin route Learning serves. The
gateway sends /api/admin/lessons/{id}/insights here with an admin principal."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import insights
from app.db import get_db
from app.platform.principal import require_principal
from app.schemas import LessonInsightsOut

router = APIRouter(dependencies=[Depends(require_principal("admin"))])


@router.get(
    "/lessons/{lesson_id}/insights",
    response_model=LessonInsightsOut,
    responses={404: {"description": "No such version (version_not_found)"}},
)
def lesson_insights(
    lesson_id: uuid.UUID,
    version: int | None = Query(None, ge=1, description="Defaults to the latest version"),
    learners: insights.Learners = Query("all", description="Everyone, or one kind of learner"),
    db: Session = Depends(get_db),
) -> insights.LessonInsights:
    """How learners do on one version of a lesson: who finished it, scores, where they
    stop, and each question's answers. No figure is given for fewer than 5 learners, and no
    learner is named. A lesson Learning has not seen published has no versions."""
    return insights.lesson_insights(db, lesson_id, version, learners)
