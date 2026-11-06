"""The aptitude question bank (SCRUM-96) and whether the aptitude test is ready (SCRUM-97).

The bank part of the monolith's aptitude.py. The quiz itself runs in Learning, from what
this module publishes:

- every question change sends content.aptitude_question.changed and then
  content.aptitude_bank.changed (readiness and the quiz's topic order), in the same
  transaction (app/events.py).
- a topic gets `assessed_at` when it first gets a question (created in it or moved into it)
  and keeps it for good, so it can never be deleted (topics.delete_topic).
"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import events
from app.models import MAX_LEVEL, MIN_LEVEL, AptitudeQuestion, Topic

# Offered last on every quiz question by Learning and always scored as wrong. Authors may
# not use its id.
NOT_SURE_OPTION = {"id": "not-sure", "text": "I’m not sure"}


class AptitudeError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def _validate_options(options) -> tuple[list[dict], str]:
    ids = [option.id.strip() for option in options]
    if len(ids) < 2:
        raise AptitudeError("options_required", "Add at least two answer options.")
    if NOT_SURE_OPTION["id"] in ids:
        raise AptitudeError(
            "option_id_reserved",
            f"The option id “{NOT_SURE_OPTION['id']}” is reserved. Use a different id.",
        )
    if len(ids) != len(set(ids)):
        raise AptitudeError("option_ids_repeated", "Each answer option needs a different id.")
    correct = [option.id.strip() for option in options if option.correct]
    if len(correct) != 1:
        raise AptitudeError("one_correct_required", "Mark exactly one answer option as correct.")
    stored = [{"id": option.id.strip(), "text": option.text.strip()} for option in options]
    if any(not option["id"] or not option["text"] for option in stored):
        raise AptitudeError("option_incomplete", "Every answer option needs text and an id.")
    return stored, correct[0]


def _topic(db: Session, topic_id: uuid.UUID) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise AptitudeError("topic_not_found", "Choose an existing topic.", 404)
    return topic


def mark_assessed(db: Session, topic_id: uuid.UUID) -> None:
    """Set the topic's `assessed_at` if it has none. Not an edit of the topic, so its
    `updated_at` stays, and nothing Learning sees changes."""
    db.execute(
        update(Topic)
        .where(Topic.id == topic_id, Topic.assessed_at.is_(None))
        .values(assessed_at=func.now(), updated_at=Topic.updated_at)
        .execution_options(synchronize_session=False)
    )


def create_question(db: Session, body) -> AptitudeQuestion:
    _topic(db, body.topic_id)
    options, correct = _validate_options(body.options)
    question = AptitudeQuestion(
        topic_id=body.topic_id,
        level=body.level,
        prompt=body.prompt.strip(),
        options=options,
        correct_option_id=correct,
        is_active=body.is_active,
    )
    db.add(question)
    mark_assessed(db, body.topic_id)
    events.question_changed(db, question, bump=False)
    events.bank_changed(db)
    db.commit()
    db.refresh(question)
    return question


def _state(question: AptitudeQuestion) -> tuple:
    return (
        question.topic_id,
        question.prompt,
        question.options,
        question.correct_option_id,
        question.is_active,
    )


def update_question(db: Session, question_id: uuid.UUID, body) -> AptitudeQuestion:
    question = db.get(AptitudeQuestion, question_id, with_for_update=True)
    if question is None:
        raise AptitudeError("question_not_found", "That question does not exist.", 404)
    before = _state(question)
    try:
        if body.topic_id is not None:
            _topic(db, body.topic_id)
            question.topic_id = body.topic_id
        if body.prompt is not None:
            question.prompt = body.prompt.strip()
        if body.options is not None:
            question.options, question.correct_option_id = _validate_options(body.options)
        if body.is_active is not None:
            question.is_active = body.is_active
    except AptitudeError:
        db.rollback()
        raise
    if _state(question) != before:
        mark_assessed(db, question.topic_id)
        events.question_changed(db, question)
        events.bank_changed(db)
    db.commit()
    db.refresh(question)
    return question


def question_out(question: AptitudeQuestion) -> dict:
    return {
        "id": question.id,
        "topic_id": question.topic_id,
        "topic_name": question.topic.name,
        "level": question.level,
        "prompt": question.prompt,
        "options": question.options,
        "correct_option_id": question.correct_option_id,
        "is_active": question.is_active,
        "updated_at": question.updated_at,
    }


def _assessed_topics(db: Session) -> list[Topic]:
    """Active topics that have at least one question, in the administrator's order."""
    return list(
        db.scalars(
            select(Topic)
            .where(
                Topic.archived_at.is_(None),
                select(AptitudeQuestion.id).where(AptitudeQuestion.topic_id == Topic.id).exists(),
            )
            .order_by(Topic.position, Topic.name)
        )
    )


def bank(db: Session) -> dict:
    questions = list(
        db.scalars(
            select(AptitudeQuestion)
            .join(Topic)
            .order_by(
                Topic.position, Topic.name, AptitudeQuestion.level, AptitudeQuestion.created_at
            )
        )
    )
    topic_rows = []
    for topic in _assessed_topics(db):
        counts = {
            level: sum(
                question.is_active and question.topic_id == topic.id and question.level == level
                for question in questions
            )
            for level in range(MIN_LEVEL, MAX_LEVEL + 1)
        }
        topic_rows.append(
            {
                "topic_id": topic.id,
                "topic_name": topic.name,
                "ready": all(counts.values()),
                "counts_by_level": counts,
            }
        )
    return {
        "ready": bool(topic_rows) and all(topic["ready"] for topic in topic_rows),
        "topics": topic_rows,
        "questions": [question_out(question) for question in questions],
    }
