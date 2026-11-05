"""Reading users' aptitude quizzes (Epic 6).

The quiz is taken once (SCRUM-113): a user has at most one completed attempt, saved with
their topic exemptions (`app/exemptions.py`). A user with no attempt has not taken it, which
after profile setup means they skipped it (SCRUM-98).
"""

import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    MAX_LEVEL,
    MIN_LEVEL,
    AptitudeAttempt,
    AptitudeQuestion,
    Topic,
)


class AptitudeError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def _validate_options(options) -> tuple[list[dict], str]:
    ids = [option.id.strip() for option in options]
    if len(ids) < 2:
        raise AptitudeError("options_required", "Add at least two answer options.")
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
    db.commit()
    db.refresh(question)
    return question


def update_question(db: Session, question_id: uuid.UUID, body) -> AptitudeQuestion:
    question = db.get(AptitudeQuestion, question_id)
    if question is None:
        raise AptitudeError("question_not_found", "That question does not exist.", 404)
    if body.topic_id is not None:
        _topic(db, body.topic_id)
        question.topic_id = body.topic_id
    if body.prompt is not None:
        question.prompt = body.prompt.strip()
    if body.options is not None:
        question.options, question.correct_option_id = _validate_options(body.options)
    if body.is_active is not None:
        question.is_active = body.is_active
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


def bank(db: Session) -> dict:
    questions = list(
        db.scalars(
            select(AptitudeQuestion)
            .join(Topic)
            .order_by(AptitudeQuestion.level, Topic.name, AptitudeQuestion.created_at)
        )
    )
    active = [question for question in questions if question.is_active]
    by_level = Counter(question.level for question in active)
    by_topic = Counter(question.topic.name for question in active)
    counts = {level: by_level[level] for level in range(MIN_LEVEL, MAX_LEVEL + 1)}
    return {
        "ready": all(counts.values()),
        "counts_by_level": counts,
        "counts_by_topic": dict(sorted(by_topic.items())),
        "questions": [question_out(question) for question in questions],
    }


def quiz_attempt(db: Session, user_id: uuid.UUID) -> AptitudeAttempt | None:
    """The user's completed quiz, or None if they have not taken it (or skipped it)."""
    return db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == user_id))


def has_taken_quiz(db: Session, user_id: uuid.UUID) -> bool:
    return quiz_attempt(db, user_id) is not None
