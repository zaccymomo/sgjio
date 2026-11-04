"""Aptitude question bank and the five-question onboarding quiz (SCRUM-96/97)."""

import random
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    MAX_LEVEL,
    MIN_LEVEL,
    AptitudeAttempt,
    AptitudeQuestion,
    Topic,
    User,
    UserType,
)


class AptitudeError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def latest_attempt(db: Session, user_id: uuid.UUID) -> AptitudeAttempt | None:
    return db.scalar(
        select(AptitudeAttempt)
        .where(AptitudeAttempt.user_id == user_id)
        .order_by(AptitudeAttempt.taken_at.desc(), AptitudeAttempt.id.desc())
        .limit(1)
    )


def attempts(db: Session, user_id: uuid.UUID) -> list[AptitudeAttempt]:
    return list(
        db.scalars(
            select(AptitudeAttempt)
            .where(AptitudeAttempt.user_id == user_id)
            .order_by(AptitudeAttempt.taken_at.desc(), AptitudeAttempt.id.desc())
        )
    )


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


def start_quiz(
    db: Session,
    user: User,
    choose: Callable[[list[AptitudeQuestion]], AptitudeQuestion] = random.choice,
) -> list[dict]:
    if user.user_type != UserType.NEWCOMER:
        raise AptitudeError("quiz_for_newcomers", "The aptitude quiz is for Newcomers.", 403)
    grouped: dict[int, list[AptitudeQuestion]] = defaultdict(list)
    for question in db.scalars(
        select(AptitudeQuestion)
        .where(AptitudeQuestion.is_active.is_(True))
        .order_by(AptitudeQuestion.created_at, AptitudeQuestion.id)
    ):
        grouped[question.level].append(question)
    missing = [level for level in range(MIN_LEVEL, MAX_LEVEL + 1) if not grouped[level]]
    if missing:
        raise AptitudeError(
            "aptitude_not_ready",
            "The quiz is not ready. "
            f"Level(s) {', '.join(map(str, missing))} have no active questions.",
            409,
        )
    selected = [choose(grouped[level]) for level in range(MIN_LEVEL, MAX_LEVEL + 1)]
    return [
        {
            "id": q.id,
            "topic": q.topic.name,
            "level": q.level,
            "prompt": q.prompt,
            "options": q.options,
        }
        for q in selected
    ]


def _awarded_level(results: list[dict]) -> int:
    """Start at Level 1 and advance for lower levels mastered in sequence."""
    level = MIN_LEVEL
    for result in sorted(results, key=lambda item: item["level"]):
        if result["level"] < MAX_LEVEL and result["correct"]:
            level += 1
        else:
            break
    return min(level, MAX_LEVEL)


def submit_quiz(db: Session, user: User, answers) -> AptitudeAttempt:
    if user.user_type != UserType.NEWCOMER:
        raise AptitudeError("quiz_for_newcomers", "The aptitude quiz is for Newcomers.", 403)
    ids = [answer.question_id for answer in answers]
    if len(ids) != 5 or len(set(ids)) != 5:
        raise AptitudeError("five_answers_required", "Answer each of the five questions once.")
    questions = {
        q.id: q for q in db.scalars(select(AptitudeQuestion).where(AptitudeQuestion.id.in_(ids)))
    }
    if len(questions) != 5 or {q.level for q in questions.values()} != set(range(1, 6)):
        raise AptitudeError("one_per_level_required", "Submit one question from every level.")
    results = []
    for answer in answers:
        question = questions[answer.question_id]
        option = next((item for item in question.options if item["id"] == answer.option_id), None)
        if option is None:
            raise AptitudeError("option_not_found", "Choose an answer offered for every question.")
        results.append(
            {
                "question_id": str(question.id),
                "topic_id": str(question.topic_id),
                "topic": question.topic.name,
                "level": question.level,
                "prompt": question.prompt,
                "option_id": option["id"],
                "option_text": option["text"],
                "correct": option["id"] == question.correct_option_id,
            }
        )
    attempt = AptitudeAttempt(user_id=user.id, level=_awarded_level(results), results=results)
    db.add(attempt)
    user.level = attempt.level
    user.intro_finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(attempt)
    return attempt


def skip_quiz(db: Session, user: User) -> None:
    if user.user_type != UserType.NEWCOMER:
        raise AptitudeError("quiz_for_newcomers", "The aptitude quiz is for Newcomers.", 403)
    user.intro_finished_at = datetime.now(UTC)
    db.commit()


def result_out(attempt: AptitudeAttempt) -> dict:
    return {
        "level": attempt.level,
        "correct": sum(1 for item in attempt.results if item.get("correct")),
        "total": len(attempt.results),
        "taken_at": attempt.taken_at,
    }
