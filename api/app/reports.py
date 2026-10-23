"""Problems learners report in lessons (SCRUM-82).

Routes stay thin: they call these functions and turn a ContentProblem into an HTTP error.

- a report is sent from one card of a lesson the learner can open, and names the version
  they were shown and the card (AC3). The version may be older than the latest, since a
  lesson can be republished while someone is reading it; it must be one of this lesson's,
  and the card must be in it.
- a reason is required and the note is optional, up to 500 characters (AC1).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learning import published_lesson
from app.lesson_doc import LessonDoc
from app.models import LessonReport, LessonVersion, ReportReason
from app.problems import card_not_found, version_not_found


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
        raise version_not_found()
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
