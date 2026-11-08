"""Learning's development seed data: the learners' side of the monolith's app/seed.py.

python -m app.cli seed      (after Identity's and Content's seeds: scripts/seed-all.sh)

- some completed lessons for the seed Newcomer, so the landing page circles show every
  state a circle can be in (SCRUM-43 AC3 to AC5). Only applied when the account has no
  progress at all, so it never overwrites real progress.
- an aptitude result (attempt and exemptions) for each test persona, or none for the one
  who skipped the quiz (SCRUM-98, SCRUM-113). Never replaces a result that exists.

Learning does not ask Identity or Content for anything. Users are found by their
deterministic ids (contracts/README.md: uuid5 of "sgjio:user:" + email), and lessons,
topics and questions through the read models, by natural keys: topics by name, lessons by
topic and title, questions by topic, level and seed_key. Safe to run more than once.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.erasure import is_erased
from app.models import (
    PUBLISHED,
    AptitudeAttempt,
    LearnableLesson,
    LearnableTopic,
    LessonCompletion,
    LessonDeck,
    QuizQuestion,
    TopicExemption,
)

# Content's seed topics, in their seed order (Content's app/seed.py TOPICS).
TOPICS = [
    "Singlish",
    "Hawker & Food",
    "Workplace",
    "Public Etiquette",
    "Festivals",
    "Getting Around",
]

# Identity's test personas (its seed creates the accounts and profiles) and the per-topic
# placement each one's quiz gave; None skipped the quiz.
TEST_USERS: dict[str, dict[str, int] | None] = {
    "starter@sgjio.example.com": {name: 1 for name in TOPICS},
    "mixed@sgjio.example.com": {
        "Singlish": 4,
        "Hawker & Food": 2,
        "Workplace": 3,
        "Public Etiquette": 1,
        "Festivals": 5,
        "Getting Around": 0,
    },
    "advanced@sgjio.example.com": {name: 4 for name in TOPICS},
    "skipped@sgjio.example.com": None,
}

# How many of each topic's lessons the demo Newcomer has finished, so the landing page
# shows every state a circle can be in: not started, in progress and complete.
SEEDED_COMPLETIONS = {
    "Singlish": 2,
    "Hawker & Food": 0,
    "Workplace": 1,
    "Public Etiquette": 3,
    "Festivals": 1,
    "Getting Around": 2,
}


class SeedError(RuntimeError):
    """The read models don't hold what the seed needs yet."""


def user_id_for(email: str) -> uuid.UUID:
    """Identity's deterministic seed id (contracts/README.md, "Seed and demo ids")."""
    return uuid.uuid5(uuid.NAMESPACE_URL, "sgjio:user:" + email.strip().lower())


def seed_learner_emails() -> list[str]:
    return [get_settings().seed_user_email, *TEST_USERS]


def _topics(db: Session) -> dict[str, LearnableTopic]:
    topics = {
        topic.name: topic
        for topic in db.scalars(select(LearnableTopic).where(LearnableTopic.deleted.is_(False)))
    }
    missing = [name for name in TOPICS if name not in topics]
    if missing:
        raise SeedError(
            f"Topics not replicated yet: {', '.join(missing)}. Run Content's seed, then "
            "`python -m app.cli wait-for-read-models`."
        )
    return topics


def _seed_completions(db: Session, user_id: uuid.UUID) -> list[str]:
    """Give the demo account some progress, but never overwrite real progress."""
    if is_erased(db, user_id) or db.scalar(
        select(func.count())
        .select_from(LessonCompletion)
        .where(LessonCompletion.user_id == user_id)
    ):
        return []

    log: list[str] = []
    for topic_name, count in SEEDED_COMPLETIONS.items():
        if count == 0:
            continue
        lessons = db.scalars(
            select(LearnableLesson)
            .join(LearnableTopic, LearnableTopic.id == LearnableLesson.topic_id)
            .where(
                LearnableTopic.name == topic_name,
                LearnableLesson.publication_state == PUBLISHED,
            )
            .order_by(LearnableLesson.display_title)
            .limit(count)
        ).all()
        for index, lesson in enumerate(lessons):
            deck = db.get(LessonDeck, lesson.latest_version_id)
            scored = deck.scored_questions if deck else 0
            # Alternate full marks and half marks, so the stored scores are not uniformly
            # perfect once tiers (SCRUM-27) start reading them.
            db.add(
                LessonCompletion(
                    user_id=user_id,
                    lesson_id=lesson.id,
                    best_correct=scored if index % 2 == 0 else scored // 2,
                    best_scored=scored,
                )
            )
        if lessons:
            log.append(f"{len(lessons)} completed lesson(s) in {topic_name}")
    return log


def _seed_test_users(db: Session, topics: dict[str, LearnableTopic]) -> list[str]:
    """Aptitude results for the test personas, never changing one that already exists."""
    names = {topic.id: name for name, topic in topics.items()}
    questions = {
        (names.get(question.topic_id), question.level): question
        for question in db.scalars(
            select(QuizQuestion)
            .where(QuizQuestion.is_active.is_(True))
            .order_by(QuizQuestion.seed_key)
        )
    }
    log: list[str] = []
    for email, placements in TEST_USERS.items():
        user_id = user_id_for(email)
        if (
            placements is None
            or is_erased(db, user_id)
            or db.scalar(select(AptitudeAttempt.id).where(AptitudeAttempt.user_id == user_id))
        ):
            continue

        results = []
        for topic_name, placement in placements.items():
            last_level = 5 if placement == 5 else placement + 1
            for level in range(1, last_level + 1):
                question = questions.get((topic_name, level))
                if question is None:
                    raise SeedError(
                        f"No active aptitude question for {topic_name} at Level {level} yet."
                    )
                correct = level <= placement
                option_id = (
                    question.correct_option_id
                    if correct
                    else next(
                        option["id"]
                        for option in question.options
                        if option["id"] != question.correct_option_id
                    )
                )
                option_text = next(
                    option["text"] for option in question.options if option["id"] == option_id
                )
                results.append(
                    {
                        "question_id": str(question.id),
                        "topic_id": str(question.topic_id),
                        "topic": topic_name,
                        "level": level,
                        "prompt": question.prompt,
                        "option_id": option_id,
                        "option_text": option_text,
                        "correct": correct,
                    }
                )

        db.add(AptitudeAttempt(user_id=user_id, results=results))
        db.flush()
        for topic_name, placement in placements.items():
            db.add(TopicExemption(user_id=user_id, topic_id=topics[topic_name].id, level=placement))
        log.append(f"aptitude result for {email}")
    return log


def seed(db: Session) -> list[str]:
    """Insert anything missing and return a short log of what was created."""
    topics = _topics(db)
    log = _seed_test_users(db, topics)
    log.extend(_seed_completions(db, user_id_for(get_settings().seed_user_email)))
    db.commit()
    return log
