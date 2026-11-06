"""Learning's event consumer: the only writer of its read models (contracts/README.md).

Queue `learning.events`, bound to `identity.user.*` and `content.#`. Every handler is
idempotent, because delivery is at least once and unordered:

- **Version guard.** Topics, lessons and aptitude questions keep the `aggregate_version`
  they were built from; an upsert applies only when the event's version is newer
  (`INSERT ... ON CONFLICT DO UPDATE ... WHERE stored.version < excluded.version`), so a
  duplicate or a stale event changes nothing. The bank uses its revision the same way.
- **Insert if absent** for immutable facts: a published version (deck), and a learner's
  registration (refused for an erased id).
- **Tombstones.** `topic.deleted` marks the topic deleted at the newer version, so a stale
  `topic.changed` can't bring it back. `user.deleted` adds the id to `erased_learners` for
  good and erases the learner's data (app/erasure.py).

Handlers read only the fields they need and ignore the rest (tolerant reader), run inside
the consumer's transaction, and never commit.
"""

import uuid
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.erasure import erase, is_erased
from app.models import (
    LearnableLesson,
    LearnableTopic,
    Learner,
    LessonDeck,
    QuizBank,
    QuizQuestion,
    TopicExemption,
)
from app.platform.consumer import Consumer

ROUTING_KEYS = ["identity.user.*", "content.#"]


class ImpossibleEvent(Exception):
    """An event that contradicts an invariant. Raising leaves it in the DLQ for a person."""


def _uuid(value) -> uuid.UUID:
    return uuid.UUID(str(value))


def _time(value) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _upsert(session: Session, model, values: dict, version_column: str = "version") -> None:
    """Insert, or update when the stored version is older (the version guard)."""
    table = model.__table__
    statement = insert(model).values(**values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[table.c.id],
            set_={key: statement.excluded[key] for key in values if key != "id"},
            where=table.c[version_column] < statement.excluded[version_column],
        )
    )


# --- Content --------------------------------------------------------------------------------


def on_topic_changed(session: Session, envelope: dict) -> None:
    data = envelope["data"]
    _upsert(
        session,
        LearnableTopic,
        {
            "id": _uuid(data["topic_id"]),
            "name": data["name"],
            "description": data.get("description") or "",
            "position": data["position"],
            "is_archived": bool(data["is_archived"]),
            "deleted": False,
            "version": envelope["aggregate_version"],
        },
    )


def on_topic_deleted(session: Session, envelope: dict) -> None:
    topic_id = _uuid(envelope["data"]["topic_id"])
    # Content refuses to delete a topic that has ever had an aptitude question, so no
    # exemption can name a deleted topic. If one does, a person needs to look: the handler
    # fails, the event ends up in the DLQ, and nothing is deleted.
    if session.scalar(select(exists().where(TopicExemption.topic_id == topic_id))):
        raise ImpossibleEvent(f"topic {topic_id} was deleted but learners have exemptions in it")
    _upsert(
        session,
        LearnableTopic,
        {
            "id": topic_id,
            # The name is unknown if the topic never reached Learning; the tombstone needs none.
            "name": "",
            "description": "",
            "position": 0,
            "is_archived": False,
            "deleted": True,
            "version": envelope["aggregate_version"],
        },
    )


def on_lesson_changed(session: Session, envelope: dict) -> None:
    data = envelope["data"]
    _upsert(
        session,
        LearnableLesson,
        {
            "id": _uuid(data["lesson_id"]),
            "key": data.get("key"),
            "topic_id": _uuid(data["topic_id"]),
            "level": data["level"],
            "position": data["position"],
            "created_at": _time(data["created_at"]),
            "display_title": data["display_title"],
            "publication_state": data["publication_state"],
            "learner_visible": bool(data["learner_visible"]),
            "first_published_at": _time(data["first_published_at"]),
            "published_at": _time(data.get("published_at")),
            "withdrawn_at": _time(data.get("withdrawn_at")),
            "latest_version_id": _uuid(data["latest_version_id"]),
            "latest_version_number": data["latest_version_number"],
            "version": envelope["aggregate_version"],
        },
    )


def on_lesson_version_published(session: Session, envelope: dict) -> None:
    data = envelope["data"]
    session.execute(
        insert(LessonDeck)
        .values(
            id=_uuid(data["version_id"]),
            lesson_id=_uuid(data["lesson_id"]),
            number=data["number"],
            title=data["title"],
            summary=data.get("summary") or "",
            published_at=_time(data["published_at"]),
            doc=data["doc"],
            questions=data.get("questions") or [],
            reading_seconds=data.get("reading_seconds") or 0,
            scored_questions=data.get("scored_questions") or 0,
            assets=data.get("assets") or {},
            cards_plain_text=data.get("cards_plain_text") or [],
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )


def on_aptitude_question_changed(session: Session, envelope: dict) -> None:
    data = envelope["data"]
    _upsert(
        session,
        QuizQuestion,
        {
            "id": _uuid(data["question_id"]),
            "topic_id": _uuid(data["topic_id"]),
            "level": data["level"],
            "prompt": data["prompt"],
            "options": [{"id": o["id"], "text": o["text"]} for o in data["options"]],
            "correct_option_id": data["correct_option_id"],
            "is_active": bool(data["is_active"]),
            "seed_key": data.get("seed_key"),
            "version": envelope["aggregate_version"],
        },
    )


def on_aptitude_bank_changed(session: Session, envelope: dict) -> None:
    data = envelope["data"]
    _upsert(
        session,
        QuizBank,
        {
            "id": _uuid(envelope["aggregate_id"]),
            "revision": envelope["aggregate_version"],
            "ready": bool(data["ready"]),
            "topics": [
                {"topic_id": str(_uuid(row["topic_id"])), "ready": bool(row["ready"])}
                for row in data["topics"]
            ],
        },
        version_column="revision",
    )


# --- Identity -------------------------------------------------------------------------------


def on_user_registered(session: Session, envelope: dict) -> None:
    data = envelope["data"]
    if data.get("role") != "user":
        return  # administrators are never learners
    user_id = _uuid(data["user_id"])
    if is_erased(session, user_id):
        return  # erasure is for good: a replayed registration brings nobody back
    session.execute(
        insert(Learner)
        .values(
            user_id=user_id,
            user_type=data["user_type"],
            registered_at=_time(data["registered_at"]),
        )
        .on_conflict_do_nothing(index_elements=["user_id"])
    )


def on_user_deleted(session: Session, envelope: dict) -> None:
    data = envelope["data"]
    erase(session, _uuid(data["user_id"]), _time(data["deleted_at"]))


HANDLERS = {
    "content.topic.changed": on_topic_changed,
    "content.topic.deleted": on_topic_deleted,
    "content.lesson.changed": on_lesson_changed,
    "content.lesson_version.published": on_lesson_version_published,
    "content.aptitude_question.changed": on_aptitude_question_changed,
    "content.aptitude_bank.changed": on_aptitude_bank_changed,
    "identity.user.registered": on_user_registered,
    "identity.user.deleted": on_user_deleted,
}

consumer = Consumer(
    routing_keys=ROUTING_KEYS,
    handlers=HANDLERS,
    session_factory=SessionLocal,
    queue="learning.events",
)
