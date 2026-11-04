"""Admin-only routes. Every route here must depend on require_admin.

Setting `dependencies` on the router means a new route added below is protected even if
its author forgets to add the guard.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app import admins, aptitude, insights, lessons, media, reports, topics
from app.auth.deps import require_admin
from app.db import get_db
from app.models import User
from app.problems import ContentProblem
from app.schemas import (
    AdminInviteRequest,
    AdminOut,
    AdminsOut,
    AptitudeBankOut,
    AptitudeQuestionCreate,
    AptitudeQuestionOut,
    AptitudeQuestionUpdate,
    AssetOut,
    LessonChangeRequest,
    LessonCreateRequest,
    LessonInsightsOut,
    LessonOrderRequest,
    LessonOut,
    LessonSummaryOut,
    LessonUpdateRequest,
    ReportOut,
    ReportStatusRequest,
    TopicOrderRequest,
    TopicOut,
    TopicRequest,
)

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


@router.get("/ping")
def admin_ping(admin: User = Depends(require_admin)) -> dict:
    """A trivial protected route, for checking the admin guard end to end."""
    return {"ok": True, "admin": admin.email}


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
    """Create a draft at the end of its topic. Every field may be empty; `doc` may hold the
    whole deck, so a script can write a lesson in one request."""
    try:
        return lessons.create_lesson(db, body.title, body.summary, body.topic_id, body.doc)
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
            "archived (topic_archived), or a published lesson would lose its topic "
            "(topic_required)"
        },
    },
)
def update_lesson(
    lesson_id: uuid.UUID, body: LessonUpdateRequest, db: Session = Depends(get_db)
) -> lessons.LessonDetail:
    """Change the draft's title, summary or cards, or the lesson's topic; fields left out
    are kept. Works whatever the status: users keep seeing the published version until the
    draft is published. A new topic moves the lesson to the end of it straight away. Send
    the `updated_at` the editor loaded."""
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
            "or it changed since it was loaded (lesson_out_of_date)"
        },
    },
)
def publish_lesson(
    lesson_id: uuid.UUID,
    body: LessonChangeRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> lessons.LessonDetail:
    """Make the draft what users see, as a new version. Safe to repeat."""
    try:
        return lessons.publish_lesson(db, lesson_id, body.updated_at, admin.id)
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


# --- Insights (SCRUM-84) -------------------------------------------------------------------


@router.get(
    "/lessons/{lesson_id}/insights",
    response_model=LessonInsightsOut,
    responses={
        404: {"description": "No such lesson or version (lesson_not_found, version_not_found)"}
    },
)
def lesson_insights(
    lesson_id: uuid.UUID,
    version: int | None = Query(None, ge=1, description="Defaults to the latest version"),
    learners: insights.Learners = Query("all", description="Everyone, or one kind of learner"),
    db: Session = Depends(get_db),
) -> insights.LessonInsights:
    """How learners do on one version of a lesson: who finished it, scores, where they
    stop, and each question's answers. No figure is given for fewer than 5 learners, and no
    learner is named."""
    try:
        return insights.lesson_insights(db, lesson_id, version, learners)
    except ContentProblem as problem:
        raise _refuse(problem) from None


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
    admin: User = Depends(require_admin),
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
        return media.store(db, data, file.filename or "", admin.id)
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
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> reports.ReportSummary:
    """Mark a report Fixed or Dismissed, which keeps it for reference (AC3), or reopen it."""
    try:
        return reports.set_status(db, admin.id, report_id, body.status)
    except ContentProblem as problem:
        raise _refuse(problem) from None


# --- Administrators (SCRUM-81) ------------------------------------------------------------

ADMIN_NOT_FOUND = {404: {"description": "No administrator with that id (admin_not_found)"}}


@router.get("/admins", response_model=AdminsOut)
def list_admins(
    admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminsPage:
    """Every administrator with their last sign-in, removed ones apart, and the latest
    changes (AC1)."""
    return admins.list_admins(db, admin)


@router.post(
    "/admins",
    response_model=AdminOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "description": "The email has an account: email_in_use (a learner's, AC3), "
            "already_admin, already_invited or admin_removed (these carry admin_id)"
        },
        422: {"description": "outside_domain until allow_other_domain is set, or a bad field"},
    },
)
def invite_admin(
    body: AdminInviteRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminSummary:
    """Create an administrator and email them a link to choose a password (AC2)."""
    try:
        invited = admins.invite_admin(db, admin, body.name, body.email, body.allow_other_domain)
    except ContentProblem as problem:
        raise _refuse(problem) from None
    return admins.get_summary(db, admin, invited.id)


@router.post(
    "/admins/{admin_id}/resend-invite",
    response_model=AdminOut,
    responses={**ADMIN_NOT_FOUND, 409: {"description": "Not waiting for an invite (not_invited)"}},
)
def resend_invite(
    admin_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminSummary:
    """Email a new invite link. The earlier one stops working."""
    try:
        admins.resend_invite(db, admin, admin_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None
    return admins.get_summary(db, admin, admin_id)


@router.post(
    "/admins/{admin_id}/remove",
    response_model=AdminOut,
    responses={
        **ADMIN_NOT_FOUND,
        409: {"description": "Yourself (cannot_remove_self) or the last one (last_admin)"},
    },
)
def remove_admin(
    admin_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminSummary:
    """Close an administrator's account, or cancel their invite: their sessions end and
    they can no longer sign in (AC4, AC5). Safe to repeat."""
    try:
        admins.remove_admin(db, admin, admin_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None
    return admins.get_summary(db, admin, admin_id)


@router.post("/admins/{admin_id}/restore", response_model=AdminOut, responses=ADMIN_NOT_FOUND)
def restore_admin(
    admin_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> admins.AdminSummary:
    """Give a removed administrator access again, with a new link to choose a password.
    Safe to repeat."""
    try:
        admins.restore_admin(db, admin, admin_id)
    except ContentProblem as problem:
        raise _refuse(problem) from None
    return admins.get_summary(db, admin, admin_id)
