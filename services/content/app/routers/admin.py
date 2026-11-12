"""Content's admin-only routes: topics, lessons, media, reported problems and the aptitude
question bank. Every route here must depend on require_admin.

Setting `dependencies` on the router means a new route added below is protected even if
its author forgets to add the guard. The administrator is the gateway's principal
(contracts/README.md, "Auth contract"): Identity checked the admin session, and Content only
needs the id, never a name.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app import aptitude, generation, lessons, media, reports, topics
from app.config import get_settings
from app.db import get_db
from app.platform.principal import Principal, require_principal
from app.problems import ContentProblem
from app.schemas import (
    AptitudeBankOut,
    AptitudeQuestionCreate,
    AptitudeQuestionOut,
    AptitudeQuestionUpdate,
    AssetOut,
    GenerationJobOut,
    GenerationQuotaOut,
    GenerationRequest,
    LessonChangeRequest,
    LessonCreateRequest,
    LessonOrderRequest,
    LessonOut,
    LessonPublishRequest,
    LessonSummaryOut,
    LessonUpdateRequest,
    ReportOut,
    ReportStatusRequest,
    TopicOrderRequest,
    TopicOut,
    TopicRequest,
)

require_admin = require_principal("admin")
router = APIRouter(dependencies=[Depends(require_admin)])


def _aptitude_call(action):
    try:
        return action()
    except aptitude.AptitudeError as error:
        raise HTTPException(
            error.status_code, detail={"code": error.code, "message": error.message}
        ) from None


@router.get("/aptitude-questions", response_model=AptitudeBankOut)
def aptitude_bank(db: Session = Depends(get_db)):
    return aptitude.bank(db)


@router.post(
    "/aptitude-questions", response_model=AptitudeQuestionOut, status_code=status.HTTP_201_CREATED
)
def add_aptitude_question(body: AptitudeQuestionCreate, db: Session = Depends(get_db)):
    return aptitude.question_out(_aptitude_call(lambda: aptitude.create_question(db, body)))


@router.patch("/aptitude-questions/{question_id}", response_model=AptitudeQuestionOut)
def edit_aptitude_question(
    question_id: uuid.UUID, body: AptitudeQuestionUpdate, db: Session = Depends(get_db)
):
    return aptitude.question_out(
        _aptitude_call(lambda: aptitude.update_question(db, question_id, body))
    )


# --- Topics (SCRUM-57) --------------------------------------------------------------------

NOT_FOUND = {404: {"description": "No topic with that id (topic_not_found)"}}
NAME_TAKEN = {409: {"description": "Another topic has that name (topic_name_taken)"}}
OUT_OF_DATE = {409: {"description": "The page's list is out of date (order_out_of_date)"}}


def _refuse(problem: ContentProblem) -> HTTPException:
    detail = {"code": problem.code, "message": problem.message, **problem.extra}
    if problem.field:
        detail["field"] = problem.field
    return HTTPException(problem.status_code, detail=detail)


def _invalid(error: ValueError) -> HTTPException:
    """A document that is well formed but cannot be stored, e.g. a repeated id or an image
    that does not exist. Answered like any other validation error, against `doc`."""
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[{"loc": ["body", "doc"], "msg": str(error), "type": "value_error"}],
    )


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
    """Add a topic at the end of the list, with an optional description (SCRUM-86)."""
    try:
        return topics.create_topic(db, body.name, body.description or "")
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.patch("/topics/{topic_id}", response_model=TopicOut, responses={**NOT_FOUND, **NAME_TAKEN})
def update_topic(
    topic_id: uuid.UUID, body: TopicRequest, db: Session = Depends(get_db)
) -> topics.TopicSummary:
    """Rename a topic and change its description. Leaving `description` out keeps it;
    an empty one clears it (SCRUM-86)."""
    try:
        return topics.update_topic(db, topic_id, body.name, body.description)
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
    responses={
        **NOT_FOUND,
        409: {
            "description": "The page was out of date (order_out_of_date), or the order mixes "
            "levels (lesson_order_mixes_levels)"
        },
    },
)
def reorder_lessons(
    body: LessonOrderRequest, db: Session = Depends(get_db)
) -> list[lessons.LessonSummary]:
    """Set the order of one topic's lessons, or of those with no topic (`topic_id: null`).
    List every lesson in that group exactly once, plus the order the page showed; a page
    that was out of date gets 409 order_out_of_date. Lessons are ordered by level first, so
    an order that puts a higher level above a lower one gets 409 lesson_order_mixes_levels.
    Returns every lesson, in order."""
    try:
        return lessons.reorder_lessons(db, body.topic_id, body.ids, body.previous_ids)
    except ContentProblem as problem:
        raise _refuse(problem) from None


# --- Writing lessons (SCRUM-19, SCRUM-64) -------------------------------------------------

LESSON_NOT_FOUND = {404: {"description": "No lesson with that id (lesson_not_found)"}}
TOPIC_REFUSED = {
    404: {"description": "No topic with that id (topic_not_found, field topic_id)"},
    409: {"description": "That topic is archived (topic_archived, field topic_id)"},
}
CHANGED = {409: {"description": "Changed since it was loaded (lesson_out_of_date)"}}


@router.post(
    "/lessons",
    response_model=LessonOut,
    status_code=status.HTTP_201_CREATED,
    responses=TOPIC_REFUSED,
)
def create_lesson(body: LessonCreateRequest, db: Session = Depends(get_db)) -> lessons.LessonDetail:
    """Create a draft at the end of its topic. `level` (1 to 5) is required; every other field
    may be empty, and `doc` may hold the whole deck, so a script can write a lesson in one
    request."""
    try:
        return lessons.create_lesson(
            db, body.title, body.summary, body.topic_id, body.doc, level=body.level
        )
    except ContentProblem as problem:
        raise _refuse(problem) from None
    except ValueError as error:
        raise _invalid(error) from None


@router.get("/lessons/{lesson_id}", response_model=LessonOut, responses=LESSON_NOT_FOUND)
def get_lesson(lesson_id: uuid.UUID, db: Session = Depends(get_db)) -> lessons.LessonDetail:
    """One lesson of any status: its draft, issues, counts and the files its cards use."""
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
            "description": "Changed since it was loaded (lesson_out_of_date), the topic is "
            "archived (topic_archived), a published lesson would lose its topic "
            "(topic_required), or a published lesson's level would change (level_locked)"
        },
    },
)
def update_lesson(
    lesson_id: uuid.UUID, body: LessonUpdateRequest, db: Session = Depends(get_db)
) -> lessons.LessonDetail:
    """Change the draft's title, summary or cards, or the lesson's topic or level; fields
    left out are kept. Works whatever the status: users keep seeing the published version
    until the draft is published. A new topic moves the lesson to the end of it straight
    away; the level can only change before the lesson is first published. Send the
    `updated_at` the editor loaded."""
    try:
        return lessons.update_lesson(db, lesson_id, body.updated_at, body.changes())
    except ContentProblem as problem:
        raise _refuse(problem) from None
    except ValueError as error:
        raise _invalid(error) from None


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


# --- Publishing (SCRUM-52, SCRUM-56, SCRUM-70) ---------------------------------------------

STATUS_REFUSED = {
    **LESSON_NOT_FOUND,
    409: {
        "description": "Changed since it was loaded (lesson_out_of_date), or not allowed in "
        "the lesson's status (lesson_status_conflict)"
    },
}


@router.post(
    "/lessons/{lesson_id}/publish",
    response_model=LessonOut,
    responses={
        **LESSON_NOT_FOUND,
        409: {
            "description": "Something still blocks it (lesson_has_blockers, with `issues`), "
            "it changed since it was loaded (lesson_out_of_date), or it is an AI draft's "
            "first publish without `reviewed: true` (review_required)"
        },
    },
)
def publish_lesson(
    lesson_id: uuid.UUID,
    body: LessonPublishRequest,
    db: Session = Depends(get_db),
    admin: Principal = Depends(require_admin),
) -> lessons.LessonDetail:
    """Make the draft what users see, as a new version. Safe to repeat. An AI draft's first
    publish needs `reviewed: true`, the editor's "I have reviewed every card"."""
    try:
        return lessons.publish_lesson(
            db, lesson_id, body.updated_at, admin.user_id, reviewed=body.reviewed
        )
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.post("/lessons/{lesson_id}/discard", response_model=LessonOut, responses=STATUS_REFUSED)
def discard_changes(
    lesson_id: uuid.UUID, body: LessonChangeRequest, db: Session = Depends(get_db)
) -> lessons.LessonDetail:
    """Put the draft back to the latest published version."""
    try:
        return lessons.discard_changes(db, lesson_id, body.updated_at)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.post("/lessons/{lesson_id}/withdraw", response_model=LessonOut, responses=STATUS_REFUSED)
def withdraw_lesson(
    lesson_id: uuid.UUID, body: LessonChangeRequest, db: Session = Depends(get_db)
) -> lessons.LessonDetail:
    """Hide a published lesson from users. Their completions and history keep it."""
    try:
        return lessons.withdraw_lesson(db, lesson_id, body.updated_at)
    except ContentProblem as problem:
        raise _refuse(problem) from None


@router.post("/lessons/{lesson_id}/restore", response_model=LessonOut, responses=STATUS_REFUSED)
def restore_lesson(
    lesson_id: uuid.UUID, body: LessonChangeRequest, db: Session = Depends(get_db)
) -> lessons.LessonDetail:
    """Show a withdrawn lesson to users again, as its latest published version."""
    try:
        return lessons.restore_lesson(db, lesson_id, body.updated_at)
    except ContentProblem as problem:
        raise _refuse(problem) from None


# --- AI drafts (docs/ai-lessons-api.md, "Content") -----------------------------------------


@router.post(
    "/lessons/generate",
    response_model=GenerationJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"description": "No such active topic (topic_not_found, field topic_id)"},
        429: {"description": "20 drafts today already (daily_limit_reached, left_today 0)"},
    },
)
def generate_draft(
    body: GenerationRequest,
    db: Session = Depends(get_db),
    admin: Principal = Depends(require_admin),
) -> dict:
    """Ask the AI for a Draft lesson from the administrator's notes. Poll
    GET /generation/{id}; when it is done, `lesson_id` is the new Draft."""
    try:
        job = generation.request_draft(
            db, admin.user_id, body.topic_id, body.level, body.notes, body.cards
        )
    except ContentProblem as problem:
        raise _refuse(problem) from None
    return generation.job_out(db, job, admin.user_id)


@router.get("/generation", response_model=GenerationQuotaOut)
def generation_quota(
    db: Session = Depends(get_db), admin: Principal = Depends(require_admin)
) -> dict:
    """How many drafts the administrator can still ask for today, for the dialog's footer."""
    return {
        "daily_limit": get_settings().generation_admin_daily_limit,
        "left_today": generation.left_today(db, admin.user_id),
    }


@router.get(
    "/generation/{job_id}",
    response_model=GenerationJobOut,
    responses={404: {"description": "No such request (generation_not_found)"}},
)
def generation_status(
    job_id: uuid.UUID, db: Session = Depends(get_db), admin: Principal = Depends(require_admin)
) -> dict:
    """A draft request's progress. One still waiting after GENERATION_TIMEOUT_SECONDS is
    failed (timeout)."""
    try:
        job = generation.get_job(db, job_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None
    return generation.job_out(db, job, admin.user_id)


# --- Images and audio (SCRUM-19) -----------------------------------------------------------


@router.post(
    "/media",
    response_model=AssetOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        413: {"description": "Over the size or length limit (media_too_large)"},
        415: {"description": "Not a supported image or audio file (media_unsupported)"},
        422: {"description": "A damaged image (media_unreadable)"},
    },
)
async def upload_media(
    file: UploadFile,
    db: Session = Depends(get_db),
    admin: Principal = Depends(require_admin),
) -> media.Asset:
    """Upload an image (JPEG, PNG, WebP) or audio (MP3, M4A, WAV, Ogg) for a card. Uploading
    a file that is already stored returns the stored one. Refer to it from a card by `id`."""
    limit = media.largest_upload_bytes()
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": "media_too_large",
                "message": f"That file is too large. The limit is {limit // (1024 * 1024)} MB.",
            },
        )
    try:
        return media.store(db, data, file.filename or "", admin.user_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None


# --- Reported problems (SCRUM-83) ---------------------------------------------------------


@router.get("/reports", response_model=list[ReportOut])
def list_reports(
    which: Literal["open", "closed"] = Query("open", alias="status"),
    db: Session = Depends(get_db),
) -> list[reports.ReportSummary]:
    """Open reports newest first (`status=open`, AC1), or those marked Fixed or Dismissed,
    most recently dealt with first (`status=closed`, AC3). Never says who sent them."""
    return reports.list_reports(db, which)


@router.put(
    "/reports/{report_id}/status",
    response_model=ReportOut,
    responses={404: {"description": "No report with that id (report_not_found)"}},
)
def set_report_status(
    report_id: uuid.UUID,
    body: ReportStatusRequest,
    admin: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> reports.ReportSummary:
    """Mark a report Fixed or Dismissed, which keeps it for reference (AC3), or reopen it."""
    try:
        return reports.set_status(db, admin.user_id, report_id, body.status)
    except ContentProblem as problem:
        raise _refuse(problem) from None
