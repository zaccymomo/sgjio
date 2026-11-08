"""The adaptive aptitude quiz and its result (SCRUM-97, SCRUM-99, SCRUM-100). Moved from the
quiz-engine half of the monolith's app/aptitude.py; the bank itself (authoring, readiness)
stays with Content.

Only a completed quiz is stored. While a learner is taking it, the browser sends the
answers so far and the server works out the next topic and difficulty without revealing
whether the last answer was right. Completing it saves an immutable answer snapshot and
one exemption level per assessed topic.

Where the facts come from now:
- whether the quiz is ready, and the order it asks topics in: `quiz_bank`, exactly as
  Content's `aptitude.bank()` decided (content.aptitude_bank.changed). Learning has no
  readiness rule of its own.
- the questions: `quiz_questions` (content.aptitude_question.changed); topic names:
  `learnable_topics`.
- who may take it: the caller's principal, from the gateway (X-User-Type and
  X-Profile-Completed), which Identity answers fresh on every request.
"""

import random
import uuid
from collections.abc import Callable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import lesson_visible, visible_to_users
from app.erasure import refuse_if_erased
from app.exemptions import is_exempted
from app.models import (
    MAX_LEVEL,
    MIN_LEVEL,
    NEWCOMER,
    AptitudeAttempt,
    LearnableLesson,
    LearnableTopic,
    LessonDeck,
    QuizBank,
    QuizQuestion,
    TopicExemption,
)
from app.platform.principal import Principal
from app.problems import aptitude_problem

# Offered last on every quiz question and always scored as wrong, so a learner who does not
# know the answer is not nudged into a lucky guess that would exempt them from lessons.
NOT_SURE_OPTION = {"id": "not-sure", "text": "I’m not sure"}

Chooser = Callable[[Sequence[QuizQuestion]], QuizQuestion]


def quiz_attempt(db: Session, user_id: uuid.UUID) -> AptitudeAttempt | None:
    return db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == user_id))


def has_taken_quiz(db: Session, user_id: uuid.UUID) -> bool:
    return quiz_attempt(db, user_id) is not None


def _eligible(db: Session, user: Principal) -> None:
    if user.user_type != NEWCOMER:
        raise aptitude_problem("quiz_for_newcomers", "The aptitude test is for Newcomers.", 403)
    if has_taken_quiz(db, user.user_id):
        raise aptitude_problem(
            "quiz_already_completed",
            "You have already completed the aptitude test.",
            409,
        )


def _changed() -> Exception:
    return aptitude_problem(
        "aptitude_not_ready", "The aptitude test's questions changed. Start it again.", 409
    )


def _ready_topics(db: Session) -> list[LearnableTopic]:
    """The topics the quiz asks about, in its order, if Content says it is ready."""
    bank = db.scalar(select(QuizBank))
    rows = list(bank.topics) if bank is not None else []
    if bank is None or not bank.ready:
        names = {
            topic.id: topic.name
            for topic in db.scalars(
                select(LearnableTopic).where(
                    LearnableTopic.id.in_([uuid.UUID(row["topic_id"]) for row in rows])
                )
            )
        }
        missing = [
            names[uuid.UUID(row["topic_id"])]
            for row in rows
            if not row["ready"] and uuid.UUID(row["topic_id"]) in names
        ]
        detail = ", ".join(missing) if missing else "all topics"
        raise aptitude_problem(
            "aptitude_not_ready",
            f"The aptitude test is not ready. Add active questions at every level for {detail}.",
            409,
        )
    topic_ids = [uuid.UUID(row["topic_id"]) for row in rows]
    topics = {
        topic.id: topic
        for topic in db.scalars(select(LearnableTopic).where(LearnableTopic.id.in_(topic_ids)))
    }
    # A topic Content counts that has not reached Learning yet: the bank is still arriving.
    if any(topic_id not in topics for topic_id in topic_ids):
        raise _changed()
    return [topics[topic_id] for topic_id in topic_ids]


def _quiz_options(question: QuizQuestion) -> list[dict]:
    """The authored options in a fresh random order, then "I'm not sure"."""
    return [*random.sample(question.options, len(question.options)), NOT_SURE_OPTION]


def _public_question(
    question: QuizQuestion, topic: LearnableTopic, topic_index: int, topic_count: int
) -> dict:
    return {
        "id": question.id,
        "topic_id": question.topic_id,
        "topic": topic.name,
        "level": question.level,
        "prompt": question.prompt,
        "options": _quiz_options(question),
        "topic_index": topic_index + 1,
        "topic_count": topic_count,
    }


def _pick(
    db: Session,
    topic: LearnableTopic,
    level: int,
    topic_index: int,
    topic_count: int,
    choose: Chooser,
) -> dict:
    choices = list(
        db.scalars(
            select(QuizQuestion)
            .where(
                QuizQuestion.topic_id == topic.id,
                QuizQuestion.level == level,
                QuizQuestion.is_active.is_(True),
            )
            # A stable order, so a seeded `choose` picks the same question every time.
            .order_by(QuizQuestion.id)
        )
    )
    if not choices:
        raise _changed()
    return _public_question(choose(choices), topic, topic_index, topic_count)


def start_quiz(db: Session, user: Principal, choose: Chooser = random.choice) -> dict:
    _eligible(db, user)
    topics = _ready_topics(db)
    return {"done": False, "question": _pick(db, topics[0], 1, 0, len(topics), choose)}


def _trace(db: Session, topics: list[LearnableTopic], answers) -> tuple[list[dict], int, int]:
    """Validate an adaptive answer path and return snapshots plus the next topic/level."""
    topic_index, level = 0, MIN_LEVEL
    results: list[dict] = []
    seen: set[uuid.UUID] = set()
    for answer in answers:
        if topic_index >= len(topics):
            raise aptitude_problem(
                "answers_after_finish",
                "Start the aptitude test again and answer each question once.",
            )
        if answer.question_id in seen:
            raise aptitude_problem("question_repeated", "Answer each question once.")
        question = db.get(QuizQuestion, answer.question_id)
        if (
            question is None
            or question.topic_id != topics[topic_index].id
            or question.level != level
        ):
            raise aptitude_problem(
                "invalid_quiz_path", "The answers do not follow the aptitude test's order."
            )
        option = next(
            (item for item in _quiz_options(question) if item["id"] == answer.option_id), None
        )
        if option is None:
            raise aptitude_problem(
                "option_not_found", "Choose an answer offered for every question."
            )
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


def next_question(db: Session, user: Principal, answers, choose: Chooser = random.choice) -> dict:
    _eligible(db, user)
    topics = _ready_topics(db)
    _, topic_index, level = _trace(db, topics, answers)
    if topic_index == len(topics):
        return {"done": True, "question": None}
    return {
        "done": False,
        "question": _pick(db, topics[topic_index], level, topic_index, len(topics), choose),
    }


def submit_quiz(db: Session, user: Principal, answers) -> AptitudeAttempt:
    _eligible(db, user)
    topics = _ready_topics(db)
    results, topic_index, _ = _trace(db, topics, answers)
    if topic_index != len(topics):
        raise aptitude_problem("quiz_incomplete", "Finish every assessed topic before submitting.")

    placements = {topic.id: 0 for topic in topics}
    for result in results:
        topic_id = uuid.UUID(result["topic_id"])
        if result["correct"]:
            placements[topic_id] = result["level"]

    refuse_if_erased(db, user.user_id)
    attempt = AptitudeAttempt(user_id=user.user_id, results=results)
    db.add(attempt)
    db.flush()
    for topic in topics:
        db.add(TopicExemption(user_id=user.user_id, topic_id=topic.id, level=placements[topic.id]))
    db.commit()
    db.refresh(attempt)
    return attempt


def result_out(db: Session, attempt: AptitudeAttempt) -> dict:
    """The quiz's placement in each topic it covered, with how many of the topic's lessons
    that exempts (SCRUM-100 AC1).

    The counts are worked out now, over currently visible lessons, so they always agree
    with the circles: a lesson published since at an exempted level counts (SCRUM-104 AC3).
    A lesson the user has also completed still counts as exempted here, so the figure does
    not shrink as they study. Topics archived since the quiz are left out, as from the
    circles.

    Each topic also lists the lessons it exempts, lowest level first as on topic pages,
    titled as their latest version reads, so the results can show which they are.
    """
    counts = {
        row.topic_id: row
        for row in db.execute(
            select(
                LearnableLesson.topic_id,
                func.count(LearnableLesson.id).label("available"),
                func.count(LearnableLesson.id)
                .filter(is_exempted(attempt.user_id))
                .label("exempted"),
            )
            .where(lesson_visible())
            .group_by(LearnableLesson.topic_id)
        )
    }
    exempted_by_topic: dict[uuid.UUID, list[dict]] = {}
    for row in db.execute(
        select(
            LearnableLesson.id, LearnableLesson.topic_id, LearnableLesson.level, LessonDeck.title
        )
        .join(LessonDeck, LessonDeck.id == LearnableLesson.latest_version_id)
        .where(lesson_visible(), is_exempted(attempt.user_id))
        .order_by(LearnableLesson.level, LearnableLesson.position, LearnableLesson.created_at)
    ):
        exempted_by_topic.setdefault(row.topic_id, []).append(
            {"id": row.id, "title": row.title, "level": row.level}
        )
    placements = list(
        db.execute(
            visible_to_users(
                select(TopicExemption, LearnableTopic)
                .join(LearnableTopic, LearnableTopic.id == TopicExemption.topic_id)
                .where(TopicExemption.user_id == attempt.user_id)
                .order_by(LearnableTopic.position, LearnableTopic.name)
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
                "lessons": exempted_by_topic.get(topic.id, []),
            }
            for exemption, topic in placements
        ],
    }
