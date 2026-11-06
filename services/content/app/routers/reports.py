"""A learner reporting a problem on a card (SCRUM-82). The rest of the learner's lesson
routes are Learning's; the gateway sends only POST /api/lessons/{id}/reports here.

The learner is the gateway's app-scope principal (contracts/README.md, "Auth contract").
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import reports
from app.db import get_db
from app.platform.principal import Principal, require_principal
from app.problems import ContentProblem
from app.schemas import ReportRequest, ReportSentOut

require_user = require_principal("app")
router = APIRouter(dependencies=[Depends(require_user)])

UNAVAILABLE = {404: {"description": "Not published, or no such lesson (lesson_unavailable)"}}


def _refuse(problem: ContentProblem) -> HTTPException:
    detail = {"code": problem.code, "message": problem.message, **problem.extra}
    if problem.field:
        detail["field"] = problem.field
    return HTTPException(problem.status_code, detail=detail)


@router.post(
    "/lessons/{lesson_id}/reports",
    response_model=ReportSentOut,
    status_code=201,
    responses={**UNAVAILABLE, 422: {"description": "Not a version or card of this lesson"}},
)
def report_problem(
    lesson_id: uuid.UUID,
    body: ReportRequest,
    user: Principal = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Report a problem on one card, naming the version shown (SCRUM-82)."""
    try:
        return reports.report_problem(
            db, user.user_id, lesson_id, body.version, body.card_id, body.reason, body.note
        )
    except ContentProblem as problem:
        raise _refuse(problem) from None
