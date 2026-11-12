"""AI-drafted lessons for administrators (docs/ai-lessons-plan.md, sections 6 and 7;
docs/ai-lessons-api.md, "Content").

- `request_draft` saves a `generation_jobs` row and writes content.lesson_generation.requested
  in the same transaction: the brief (topic, level, length, the administrator's notes) and
  the grounding (the topic's published lessons). It never carries who asked.
- Generation answers with generation.lesson.progress, then .generated or .failed, all with
  requester "content". The consumer applies only events newer than the job holds, and only
  while it is waiting, so repeats and late results change nothing.
- .generated becomes an ordinary Draft through `lessons.add_draft`, with `origin = "ai"`.
  Its first publish needs the review tick (lessons.publish_lesson).
- 20 requests a day per administrator, by Singapore date; failed ones don't count.
- A job still waiting GENERATION_TIMEOUT_SECONDS (180 in compose) after it was made is
  marked failed ("timeout") whenever it is read. No scheduler.
"""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import lesson_doc, lessons
from app.config import get_settings
from app.lesson_doc import LessonDoc
from app.models import (
    GenerationJob,
    GenerationStatus,
    Lesson,
    LessonOrigin,
    LessonStatus,
    Topic,
)
from app.platform.outbox import emit
from app.problems import ContentProblem, topic_not_found

REQUESTED = "content.lesson_generation.requested"
PROGRESS = "generation.lesson.progress"
GENERATED = "generation.lesson.generated"
FAILED = "generation.lesson.failed"

SINGAPORE = ZoneInfo("Asia/Singapore")
QUESTIONS_FOR_CARDS = {4: 1, 6: 2, 8: 3}
WAITING = (GenerationStatus.REQUESTED, GenerationStatus.WRITING)
MAX_GROUNDING_LESSONS = 20
MAX_CARDS_TEXT = 30
MAX_AVOID_TITLES = 50

# What the dialog says for each failure code, in plain words (never the model's text).
FAILURE_MESSAGES = {
    "off_topic": "No draft was created: the notes were not recognised as a topic about "
    "everyday life in Singapore. Please rephrase them and try again.",
    "invalid_output": "The draft did not pass our quality checks and was not saved. Please "
    "try again, ideally with more specific notes.",
    "unsafe": "The draft did not pass our quality checks and was not saved. Please try "
    "again, ideally with more specific notes.",
    "provider": "The AI service is unavailable at the moment. Please try again shortly.",
    "timeout": "The AI service took too long to respond. Please try again shortly.",
}


def daily_limit_reached(limit: int) -> ContentProblem:
    return ContentProblem(
        "daily_limit_reached",
        f"You have reached today's limit of {limit} AI drafts. You can generate more tomorrow.",
        429,
        extra={"left_today": 0},
    )


def generation_not_found() -> ContentProblem:
    return ContentProblem("generation_not_found", "We couldn't find that draft request.", 404)


# --- Limit and timeout ---------------------------------------------------------------------


def _expire(job: GenerationJob, now: datetime) -> None:
    """Mark a job that has waited too long as failed (timeout)."""
    timeout = timedelta(seconds=get_settings().generation_timeout_seconds)
    if job.status in WAITING and job.created_at + timeout < now:
        job.status = GenerationStatus.FAILED
        job.failure_code = "timeout"
        job.finished_at = now


def left_today(db: Session, admin_id: uuid.UUID) -> int:
    """Requests the administrator has left today (Singapore date). Failed ones, including
    those that have timed out by now, don't count."""
    now = datetime.now(UTC)
    start = (
        now.astimezone(SINGAPORE).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
    cutoff = now - timedelta(seconds=get_settings().generation_timeout_seconds)
    used = db.scalar(
        select(func.count())
        .select_from(GenerationJob)
        .where(
            GenerationJob.requested_by == admin_id,
            GenerationJob.created_at >= start,
            GenerationJob.status != GenerationStatus.FAILED,
            # Waiting longer than the timeout: as good as failed.
            ~(GenerationJob.status.in_(WAITING) & (GenerationJob.created_at < cutoff)),
        )
    )
    return max(get_settings().generation_admin_daily_limit - used, 0)


# --- The request ---------------------------------------------------------------------------


def _grounding(db: Session, topic: Topic, level: int) -> dict:
    """The topic's published lessons (latest versions, nearest `level` first) and every
    lesson title in it, so the AI agrees with them and doesn't repeat a title."""
    published = db.scalars(
        select(Lesson)
        .where(Lesson.topic_id == topic.id, Lesson.status == LessonStatus.PUBLISHED)
        .order_by(Lesson.level, Lesson.position, Lesson.created_at)
    ).all()
    published.sort(key=lambda lesson: abs(lesson.level - level))
    grounding_lessons = []
    for lesson in published[:MAX_GROUNDING_LESSONS]:
        version = lessons.latest_version(db, lesson.id)
        if version is None:
            continue
        cards = version.doc.get("cards", [])[:MAX_CARDS_TEXT]
        grounding_lessons.append(
            {
                "title": version.title,
                "summary": version.summary,
                "level": lesson.level,
                "cards_text": [lesson_doc.plain_text(card.get("text", "")) for card in cards],
            }
        )
    titles = db.scalars(
        select(Lesson.title)
        .where(Lesson.topic_id == topic.id, Lesson.title != "")
        .order_by(Lesson.level, Lesson.position, Lesson.created_at)
    ).all()
    return {
        "lessons": grounding_lessons,
        "mistakes": [],
        "avoid_titles": list(dict.fromkeys(titles))[:MAX_AVOID_TITLES],
        "feedback": [],
    }


def request_draft(
    db: Session, admin_id: uuid.UUID, topic_id: uuid.UUID, level: int, notes: str, cards: int
) -> GenerationJob:
    """Save the request and send it to Generation, in one transaction."""
    try:
        topic = db.get(Topic, topic_id)
        if topic is None or topic.archived_at is not None:
            raise topic_not_found(field="topic_id")
        # One request at a time per administrator, so two quick clicks can't pass the limit.
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"generation:{admin_id}"},
        )
        if left_today(db, admin_id) <= 0:
            raise daily_limit_reached(get_settings().generation_admin_daily_limit)
        job = GenerationJob(
            requested_by=admin_id, topic_id=topic.id, level=level, cards=cards, notes=notes
        )
        db.add(job)
        db.flush()
        emit(
            db,
            type=REQUESTED,
            aggregate_type="lesson_generation",
            aggregate_id=job.id,
            aggregate_version=1,
            data={
                "request_id": job.id,
                "brief": {
                    "audience": "admin",
                    "focus": "notes",
                    "topic": {
                        "id": topic.id,
                        "name": topic.name,
                        "description": topic.description,
                    },
                    "level": level,
                    "cards": cards,
                    "questions": QUESTIONS_FOR_CARDS[cards],
                    "ask": None,
                    "notes": notes,
                    "check_answers": False,
                },
                "grounding": _grounding(db, topic, level),
            },
        )
    except ContentProblem:
        db.rollback()
        raise
    db.commit()
    return job


def get_job(db: Session, job_id: uuid.UUID) -> GenerationJob:
    """A job, with the timeout applied (and saved) if it has waited too long."""
    job = db.get(GenerationJob, job_id, with_for_update=True)
    if job is None:
        db.rollback()
        raise generation_not_found()
    _expire(job, datetime.now(UTC))
    db.commit()
    return job


def job_out(db: Session, job: GenerationJob, admin_id: uuid.UUID) -> dict:
    failure = None
    if job.status == GenerationStatus.FAILED:
        code = job.failure_code or "provider"
        failure = {
            "code": code,
            "message": FAILURE_MESSAGES.get(code, FAILURE_MESSAGES["provider"]),
        }
    return {
        "id": job.id,
        "status": job.status.value,
        "lesson_id": job.lesson_id,
        "failure": failure,
        "left_today": left_today(db, admin_id),
    }


# --- Generation's answers (app/consumers.py) ------------------------------------------------


def _waiting_job(db: Session, envelope: dict) -> GenerationJob | None:
    """The job an event is for, locked, if it is ours, still waiting and the event is newer
    than the last one applied; otherwise None (the event is ignored)."""
    data = envelope["data"]
    if data.get("requester") != "content":
        return None
    job = db.get(GenerationJob, uuid.UUID(data["request_id"]), with_for_update=True)
    if job is None:
        return None
    _expire(job, datetime.now(UTC))
    if job.status not in WAITING or envelope["aggregate_version"] <= job.progress_version:
        return None
    job.progress_version = envelope["aggregate_version"]
    return job


def on_progress(db: Session, envelope: dict) -> None:
    job = _waiting_job(db, envelope)
    if job is not None:
        job.status = GenerationStatus.WRITING


def _draft_doc(doc: dict) -> LessonDoc:
    """The generated deck as a Content draft: the same shape, with Content's own ids and no
    images or audio."""
    parsed = LessonDoc.model_validate(doc)
    for card in parsed.cards:
        card.id = None
        card.image = None
        card.audio = None
        if card.question is not None:
            card.question.id = None
            for option in card.question.options:
                option.id = None
    return lesson_doc.assign_ids(parsed)


def on_generated(db: Session, envelope: dict) -> None:
    job = _waiting_job(db, envelope)
    if job is None:
        return
    data = envelope["data"]
    now = datetime.now(UTC)
    try:
        lesson = lessons.add_draft(
            db,
            title=data["title"].strip(),
            summary=data["summary"].strip(),
            topic_id=job.topic_id,
            doc=_draft_doc(data["doc"]),
            level=job.level,
            origin=LessonOrigin.AI,
        )
    except (ContentProblem, ValueError):
        # The topic was archived or deleted meanwhile, or the deck can't be stored.
        job.status = GenerationStatus.FAILED
        job.failure_code = "invalid_output"
        job.finished_at = now
        return
    job.status = GenerationStatus.DONE
    job.lesson_id = lesson.id
    job.finished_at = now


def on_failed(db: Session, envelope: dict) -> None:
    job = _waiting_job(db, envelope)
    if job is not None:
        job.status = GenerationStatus.FAILED
        job.failure_code = envelope["data"]["code"]
        job.finished_at = datetime.now(UTC)
