"""Content's published language: what its events say about topics, lessons, versions and the
aptitude bank (contracts/events/content.*.schema.json).

Everything Learning needs is worked out here, by Content's own rules, so Learning never needs
lesson_doc.py, media.py or the bank's readiness rule:

- `learner_visible` is the single definition of "a learner may open this lesson". Reports
  (app/reports.py) use it, and its result travels in content.lesson.changed.
- `version_projection` carries each question's `scored` and `correct_option_id`, the
  reading time (which needs audio lengths), the assets and each card's plain text.
- `bank_projection` is the readiness and quiz topic order of aptitude.bank().

These return plain dicts that may still hold UUIDs and datetimes; the outbox turns them into
JSON (app/platform/outbox.py).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import lesson_doc, media
from app.lesson_doc import LessonDoc
from app.models import AptitudeQuestion, Lesson, LessonStatus, LessonVersion, Topic

# aggregate_id of content.aptitude_bank.changed: uuid5(NAMESPACE_URL, "sgjio:aptitude-bank").
APTITUDE_BANK_ID = uuid.uuid5(uuid.NAMESPACE_URL, "sgjio:aptitude-bank")


def learner_visible(lesson: Lesson, topic: Topic | None) -> bool:
    """Published, in a topic that is not archived. `topic` is the lesson's topic."""
    return (
        lesson.status == LessonStatus.PUBLISHED and topic is not None and topic.archived_at is None
    )


def lesson_topic(db: Session, lesson: Lesson) -> Topic | None:
    """The lesson's current topic, by id, so a topic just changed in this session counts
    even before the relationship is reloaded."""
    return db.get(Topic, lesson.topic_id) if lesson.topic_id is not None else None


def topic_projection(topic: Topic) -> dict:
    return {
        "topic_id": topic.id,
        "name": topic.name,
        "description": topic.description,
        "position": topic.position,
        "is_archived": topic.archived_at is not None,
    }


def _versions(db: Session, lesson_id: uuid.UUID) -> tuple[LessonVersion, LessonVersion] | None:
    """The lesson's first and latest versions, or None if it was never published."""
    rows = list(
        db.scalars(
            select(LessonVersion)
            .where(LessonVersion.lesson_id == lesson_id)
            .order_by(LessonVersion.number)
        )
    )
    return (rows[0], rows[-1]) if rows else None


def lesson_projection(db: Session, lesson: Lesson) -> dict | None:
    """content.lesson.changed's data, or None for a lesson never published (never sent).

    Pending changes must be flushed first: the versions are read from the database."""
    versions = _versions(db, lesson.id)
    if versions is None or lesson.topic_id is None:
        # Never published, so never sent. (A published lesson always keeps a topic; rows
        # built by hand without one cannot be described to Learning either.)
        return None
    first, latest = versions
    state = "withdrawn" if lesson.status == LessonStatus.WITHDRAWN else "published"
    return {
        "lesson_id": lesson.id,
        "key": lesson.key,
        "topic_id": lesson.topic_id,
        "level": lesson.level,
        "position": lesson.position,
        "created_at": lesson.created_at,
        "display_title": lesson.title,
        "publication_state": state,
        "learner_visible": learner_visible(lesson, lesson_topic(db, lesson)),
        "first_published_at": first.published_at,
        "published_at": lesson.published_at,
        "withdrawn_at": lesson.withdrawn_at,
        "latest_version_id": latest.id,
        "latest_version_number": latest.number,
    }


def _asset(asset: media.Asset) -> dict:
    """Exactly the AssetOut the front ends receive."""
    return {
        "id": asset.id,
        "kind": asset.kind.value,
        "mime": asset.mime,
        "url": asset.url,
        "size": asset.size,
        "width": asset.width,
        "height": asset.height,
        "duration_ms": asset.duration_ms,
        "placeholder": asset.placeholder,
        "color": asset.color,
        "filename": asset.filename,
    }


def _question(card: lesson_doc.Card) -> dict:
    question = card.question
    correct = lesson_doc.correct_option(question)
    if correct is None:  # publishing refuses this (question_no_correct), so never expected
        raise ValueError(f"question {question.id} on card {card.id} has no correct option")
    return {
        "card_id": card.id,
        "question_id": question.id,
        "scored": lesson_doc.is_scored(question),
        "correct_option_id": correct.id,
    }


def version_projection(db: Session, version: LessonVersion) -> dict:
    """content.lesson_version.published's data. `doc` is the stored document unchanged."""
    doc = LessonDoc.model_validate(version.doc)
    facts = media.facts_for(db, doc)
    stats = lesson_doc.stats(doc, facts)
    return {
        "version_id": version.id,
        "lesson_id": version.lesson_id,
        "number": version.number,
        "title": version.title,
        "summary": version.summary,
        "published_at": version.published_at,
        "doc": version.doc,
        "questions": [_question(card) for card in doc.cards if card.question is not None],
        "reading_seconds": stats.reading_seconds,
        "scored_questions": stats.scored_questions,
        "assets": {key: _asset(asset) for key, asset in media.assets_for(db, doc).items()},
        "cards_plain_text": [lesson_doc.plain_text(card.text) for card in doc.cards],
    }


def question_projection(question: AptitudeQuestion) -> dict:
    return {
        "question_id": question.id,
        "topic_id": question.topic_id,
        "level": question.level,
        "prompt": question.prompt,
        "options": [{"id": option["id"], "text": option["text"]} for option in question.options],
        "correct_option_id": question.correct_option_id,
        "is_active": question.is_active,
        "seed_key": question.seed_key,
    }


def bank_projection(db: Session) -> dict:
    """aptitude.bank()'s readiness, with its topics in quiz order (position, then name)."""
    from app.aptitude import bank  # aptitude emits events, which use this module

    status = bank(db)
    return {
        "ready": status["ready"],
        "topics": [
            {"topic_id": row["topic_id"], "ready": row["ready"]} for row in status["topics"]
        ],
    }
