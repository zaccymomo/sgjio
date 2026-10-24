"""Problems learners report in lessons (SCRUM-82), and administrators dealing with them
(SCRUM-83).

Routes stay thin: they call these functions and turn a ContentProblem into an HTTP error.

- a report is sent from one card of a lesson the learner can open, and names the version
  they were shown and the card (AC3). The version may be older than the latest, since a
  lesson can be republished while someone is reading it; it must be one of this lesson's,
  and the card must be in it.
- a reason is required and the note is optional, up to 500 characters (AC1).
- administrators see open reports newest first, with the lesson, the card, the reason, the
  note and the date, and never who sent them (SCRUM-83 AC1). Marking one Fixed or Dismissed
  takes it off the open list but keeps it, newest dealt with first, for reference (AC3); it
  can be reopened.
- a report points at a card by its id, which stays the same across edits, so the editor can
  open that card in today's draft (AC2). `card_in_draft` says whether it is still there.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.learning import published_lesson
from app.lesson_doc import LessonDoc
from app.models import Lesson, LessonReport, LessonVersion, ReportReason, ReportStatus, Topic
from app.problems import card_not_found, report_not_found, reported_version_not_found

# How much of a card's text the list shows.
EXCERPT_LENGTH = 140
_BLANK = re.compile(r"\{\{\s*blank\s*\}\}")
_MARKS = re.compile(r"[*_]+")


@dataclass(frozen=True)
class ReportSummary:
    id: uuid.UUID
    lesson_id: uuid.UUID
    # The lesson's title as administrators edit it now.
    lesson_title: str
    topic_name: str | None
    # The version the learner was shown, and the card's place in it (1-based).
    version: int
    card_id: str
    card_number: int | None
    card_excerpt: str
    # Whether the card is still in the draft, so the editor can open it.
    card_in_draft: bool
    reason: ReportReason
    note: str
    status: ReportStatus
    created_at: datetime
    resolved_at: datetime | None


def report_problem(
    db: Session,
    user_id: uuid.UUID,
    lesson_id: uuid.UUID,
    version: int,
    card_id: str,
    reason: ReportReason,
    note: str,
) -> LessonReport:
    """Record a learner's report on one card (SCRUM-82 AC2, AC3)."""
    lesson = published_lesson(db, lesson_id)
    shown = db.scalar(
        select(LessonVersion).where(
            LessonVersion.lesson_id == lesson.id, LessonVersion.number == version
        )
    )
    if shown is None:
        raise reported_version_not_found()
    if not any(card.id == card_id for card in LessonDoc.model_validate(shown.doc).cards):
        raise card_not_found()
    report = LessonReport(
        lesson_id=lesson.id,
        version_id=shown.id,
        card_id=card_id,
        reason=reason,
        note=note,
        reporter_id=user_id,
    )
    db.add(report)
    db.commit()
    return report


# --- Administrators (SCRUM-83) -------------------------------------------------------------


def _excerpt(text: str) -> str:
    plain = " ".join(_BLANK.sub("___", _MARKS.sub("", text)).split())
    if len(plain) <= EXCERPT_LENGTH:
        return plain
    return plain[: EXCERPT_LENGTH - 1].rstrip() + "…"


def _summary(report: LessonReport, topic_name: str | None) -> ReportSummary:
    shown = LessonDoc.model_validate(report.version.doc).cards
    number = next((n for n, card in enumerate(shown, 1) if card.id == report.card_id), None)
    draft_ids = {card.get("id") for card in report.lesson.draft.get("cards", [])}
    return ReportSummary(
        id=report.id,
        lesson_id=report.lesson_id,
        lesson_title=report.lesson.title,
        topic_name=topic_name,
        version=report.version.number,
        card_id=report.card_id,
        card_number=number,
        card_excerpt=_excerpt(shown[number - 1].text) if number else "",
        card_in_draft=report.card_id in draft_ids,
        reason=report.reason,
        note=report.note,
        status=report.status,
        created_at=report.created_at,
        resolved_at=report.resolved_at,
    )


def list_reports(db: Session, which: Literal["open", "closed"]) -> list[ReportSummary]:
    """Open reports, newest first (AC1), or those dealt with, most recently dealt with first."""
    query = (
        select(LessonReport, Topic.name)
        .join(Lesson, LessonReport.lesson_id == Lesson.id)
        .outerjoin(Topic, Lesson.topic_id == Topic.id)
    )
    if which == "open":
        query = query.where(LessonReport.status == ReportStatus.OPEN).order_by(
            LessonReport.created_at.desc(), LessonReport.id
        )
    else:
        query = query.where(LessonReport.status != ReportStatus.OPEN).order_by(
            LessonReport.resolved_at.desc(), LessonReport.id
        )
    return [_summary(report, topic_name) for report, topic_name in db.execute(query).all()]


def set_status(
    db: Session, admin_id: uuid.UUID, report_id: uuid.UUID, status: ReportStatus
) -> ReportSummary:
    """Mark a report Fixed or Dismissed (AC3), or reopen it."""
    report = db.get(LessonReport, report_id)
    if report is None:
        raise report_not_found()
    if report.status != status:
        report.status = status
        closed = status != ReportStatus.OPEN
        report.resolved_at = datetime.now(UTC) if closed else None
        report.resolved_by = admin_id if closed else None
        db.commit()
    topic = report.lesson.topic
    return _summary(report, topic.name if topic else None)


def open_report_counts(db: Session) -> dict[uuid.UUID, int]:
    """How many open reports each lesson has, for the lesson list (AC4)."""
    rows = db.execute(
        select(LessonReport.lesson_id, func.count())
        .where(LessonReport.status == ReportStatus.OPEN)
        .group_by(LessonReport.lesson_id)
    ).all()
    return {lesson_id: count for lesson_id, count in rows}
