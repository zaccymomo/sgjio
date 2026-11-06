"""Per-topic aptitude question bank and adaptive onboarding quiz (SCRUM-96/97).

Only a completed quiz is stored. While a learner is taking it, the browser sends the
answers so far and the server works out the next topic and difficulty without revealing
whether the last answer was right. Completing it saves an immutable answer snapshot and
one exemption level per assessed topic.
"""

import random
import uuid
from collections.abc import Callable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.exemptions import is_exempted
from app.models import (
    MAX_LEVEL,
    MIN_LEVEL,
    AptitudeAttempt,
    AptitudeQuestion,
    Lesson,
    LessonStatus,
    Topic,
    TopicExemption,
    User,
    UserType,
)
from app.topics import visible_to_users

# Offered last on every quiz question and always scored as wrong, so a learner who does not
# know the answer is not nudged into a lucky guess that would exempt them from lessons.
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


def quiz_attempt(db: Session, user_id: uuid.UUID) -> AptitudeAttempt | None:
    return db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == user_id))


def has_taken_quiz(db: Session, user_id: uuid.UUID) -> bool:
    return quiz_attempt(db, user_id) is not None


def _eligible(db: Session, user: User) -> None:
    if user.user_type != UserType.NEWCOMER:
        raise AptitudeError("quiz_for_newcomers", "The aptitude test is for Newcomers.", 403)
    if has_taken_quiz(db, user.id):
        raise AptitudeError(
            "quiz_already_completed",
            "You have already completed the aptitude test.",
            409,
        )


def _ready_topics(db: Session) -> list[Topic]:
    status = bank(db)
    if not status["ready"]:
        missing = [row["topic_name"] for row in status["topics"] if not row["ready"]]
        detail = ", ".join(missing) if missing else "all topics"
        raise AptitudeError(
            "aptitude_not_ready",
            f"The aptitude test is not ready. Add active questions at every level for {detail}.",
            409,
        )
    topic_ids = [row["topic_id"] for row in status["topics"]]
    topics = {topic.id: topic for topic in _assessed_topics(db)}
    return [topics[topic_id] for topic_id in topic_ids]


def _quiz_options(question: AptitudeQuestion) -> list[dict]:
    """The authored options in a fresh random order, then "I'm not sure"."""
    return [*random.sample(question.options, len(question.options)), NOT_SURE_OPTION]


def _public_question(question: AptitudeQuestion, topic_index: int, topic_count: int) -> dict:
    return {
        "id": question.id,
        "topic_id": question.topic_id,
        "topic": question.topic.name,
        "level": question.level,
        "prompt": question.prompt,
        "options": _quiz_options(question),
        "topic_index": topic_index + 1,
        "topic_count": topic_count,
    }


def _pick(
    db: Session,
    topic: Topic,
    level: int,
    topic_index: int,
    topic_count: int,
    choose: Callable[[Sequence[AptitudeQuestion]], AptitudeQuestion],
) -> dict:
    choices = list(
        db.scalars(
            select(AptitudeQuestion).where(
                AptitudeQuestion.topic_id == topic.id,
                AptitudeQuestion.level == level,
                AptitudeQuestion.is_active.is_(True),
            )
        )
    )
    if not choices:
        raise AptitudeError(
            "aptitude_not_ready", "The aptitude test's questions changed. Start it again.", 409
        )
    return _public_question(choose(choices), topic_index, topic_count)


def start_quiz(
    db: Session,
    user: User,
    choose: Callable[[Sequence[AptitudeQuestion]], AptitudeQuestion] = random.choice,
) -> dict:
    _eligible(db, user)
    topics = _ready_topics(db)
    return {"done": False, "question": _pick(db, topics[0], 1, 0, len(topics), choose)}


def _trace(db: Session, topics: list[Topic], answers) -> tuple[list[dict], int, int]:
    """Validate an adaptive answer path and return snapshots plus the next topic/level."""
    topic_index, level = 0, MIN_LEVEL
    results: list[dict] = []
    seen: set[uuid.UUID] = set()
    for answer in answers:
        if topic_index >= len(topics):
            raise AptitudeError(
                "answers_after_finish",
                "Start the aptitude test again and answer each question once.",
            )
        if answer.question_id in seen:
            raise AptitudeError("question_repeated", "Answer each question once.")
        question = db.get(AptitudeQuestion, answer.question_id)
        if (
            question is None
            or question.topic_id != topics[topic_index].id
            or question.level != level
        ):
            raise AptitudeError(
                "invalid_quiz_path", "The answers do not follow the aptitude test's order."
            )
        option = next(
            (item for item in _quiz_options(question) if item["id"] == answer.option_id), None
        )
        if option is None:
            raise AptitudeError("option_not_found", "Choose an answer offered for every question.")
        correct = option["id"] == question.correct_option_id
        results.append(
            {
                "question_id": str(question.id),
                "topic_id": str(question.topic_id),
                "topic": topics[topic_index].name,
                "level": question.level,
                "prompt": question.prompt,
                "option_id": option["id"],
                "option_text": option["text"],
                "correct": correct,
            }
        )
        seen.add(question.id)
        if correct and level < MAX_LEVEL:
            level += 1
        else:
            topic_index += 1
            level = MIN_LEVEL
    return results, topic_index, level


def next_question(
    db: Session,
    user: User,
    answers,
    choose: Callable[[Sequence[AptitudeQuestion]], AptitudeQuestion] = random.choice,
) -> dict:
    _eligible(db, user)
    topics = _ready_topics(db)
    _, topic_index, level = _trace(db, topics, answers)
    if topic_index == len(topics):
        return {"done": True, "question": None}
    return {
        "done": False,
        "question": _pick(db, topics[topic_index], level, topic_index, len(topics), choose),
    }


def submit_quiz(db: Session, user: User, answers) -> AptitudeAttempt:
    _eligible(db, user)
    topics = _ready_topics(db)
    results, topic_index, _ = _trace(db, topics, answers)
    if topic_index != len(topics):
        raise AptitudeError("quiz_incomplete", "Finish every assessed topic before submitting.")

    placements = {topic.id: 0 for topic in topics}
    for result in results:
        topic_id = uuid.UUID(result["topic_id"])
        if result["correct"]:
            placements[topic_id] = result["level"]

    attempt = AptitudeAttempt(user_id=user.id, results=results)
    db.add(attempt)
    db.flush()
    for topic in topics:
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=placements[topic.id]))
    db.commit()
    db.refresh(attempt)
    return attempt


def result_out(db: Session, attempt: AptitudeAttempt) -> dict:
    """The quiz's placement in each topic it covered, with how many of the topic's lessons
    that exempts (SCRUM-100 AC1).

    The counts are worked out now, over currently published lessons, so they always agree
    with the circles: a lesson published since at an exempted level counts (SCRUM-104 AC3).
    A lesson the user has also completed still counts as exempted here, so the figure does
    not shrink as they study. Topics archived since the quiz are left out, as from the
    circles.
    """
    published = Lesson.status == LessonStatus.PUBLISHED
    counts = {
        row.topic_id: row
        for row in db.execute(
            select(
                Lesson.topic_id,
                func.count(Lesson.id).label("available"),
                func.count(Lesson.id).filter(is_exempted(attempt.user_id)).label("exempted"),
            )
            .where(published)
            .group_by(Lesson.topic_id)
        )
    }
    placements = list(
        db.execute(
            visible_to_users(
                select(TopicExemption, Topic)
                .join(Topic, Topic.id == TopicExemption.topic_id)
                .where(TopicExemption.user_id == attempt.user_id)
                .order_by(Topic.position, Topic.name)
            )
        )
    )
    return {
        "taken_at": attempt.taken_at,
        "correct": sum(1 for result in attempt.results if result.get("correct")),
        "total": len(attempt.results),
        "placements": [
            {
                "topic_id": exemption.topic_id,
                "topic": topic.name,
                "level": exemption.level,
                "exempted": counts[topic.id].exempted if topic.id in counts else 0,
                "available": counts[topic.id].available if topic.id in counts else 0,
            }
            for exemption, topic in placements
        ],
    }
