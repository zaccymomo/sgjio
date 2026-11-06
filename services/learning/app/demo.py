"""Demo learners' lesson runs, so lesson insights (SCRUM-84) have something to show. The
Learning half of the monolith's app/demo.py.

    identity  python -m app.cli clear-demo-learners          (user.deleted: Learning erases them)
    identity  python -m app.cli seed-demo-learners           (prints its run nonce)
    learning  python -m app.cli demo-activity --run-nonce N [--count 60]
                                                             (waits for them, adds their runs)

- Identity creates `count` demo learners (default 60: two thirds newcomers, rounded, the
  rest Singaporeans, as in services/identity/app/demo.py) learner01.. at
  demo.sgjio.example.com, with ids uuid5(NAMESPACE_URL, "sgjio:user:" + email + ":" + nonce)
  (contracts/README.md), so a new run never collides with the erased ids of the last one.
  Learning works out the same ids from the nonce and count, waits until all of them have
  arrived, and takes each one's kind from their identity.user.registered event. Pass the
  same --count to both commands.
- it gives them runs through every visible lesson over the last 12 weeks, ending today. A
  lesson's versions take turns: the first version is live first, the newest last.
- answers follow simple rules: each question has a difficulty, Singaporeans know Singlish,
  later versions are a little clearer, some learners stop half way, and some retake a
  lesson they got wrong and do better. A few questions are made confusing on purpose
  (STORIES), so the demo has something to find.
- running it again with the same nonce replaces those learners' runs; nobody else's data is
  touched.
"""

import random
import time
import uuid
import zlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import deck
from app.catalog import lesson_visible, visible_to_users
from app.models import (
    SINGAPOREAN,
    AttemptAnswer,
    LearnableLesson,
    LearnableTopic,
    Learner,
    LessonAttempt,
    LessonCompletion,
    LessonDeck,
)

DOMAIN = "demo.sgjio.example.com"
DEFAULT_COUNT = 60  # 40 newcomers and 20 Singaporeans, as Identity's seed-demo-learners
WEEKS = 12

# (lesson title, question number): how often newcomers get it right first time, and the
# wrong option most of the others pick.
STORIES = {
    ("Lah, Leh and Lor", 2): (0.3, "They fully agree"),
    ("Saying No Without Saying No", 1): (0.3, "They need one more day"),
    ("Paying for Public Transport", 1): (0.35, "You're charged a flat minimum fare"),
}

# Hours of the day people learn, in Singapore: mostly lunchtime and evenings.
HOURS = [7, 8, 12, 12, 13, 13, 18, 19, 20, 20, 21, 21, 22, 22, 23]
SINGAPORE = timedelta(hours=8)


class DemoLearnersMissing(RuntimeError):
    pass


def newcomer_count(count: int = DEFAULT_COUNT) -> int:
    """How many of `count` demo learners Identity makes Newcomers (the first ones)."""
    return round(count * 2 / 3)


def demo_emails(count: int = DEFAULT_COUNT) -> list[str]:
    return [f"learner{n:02}@{DOMAIN}" for n in range(1, count + 1)]


def demo_user_ids(nonce: str, count: int = DEFAULT_COUNT) -> list[uuid.UUID]:
    """Identity's ids for this run's demo learners (contracts/README.md)."""
    return [
        uuid.uuid5(uuid.NAMESPACE_URL, f"sgjio:user:{email}:{nonce}")
        for email in demo_emails(count)
    ]


def wait_for_learners(
    db: Session, ids: list[uuid.UUID], timeout: float, poll: float = 1.0
) -> dict[uuid.UUID, str]:
    """The demo learners' kinds, once every one has arrived (identity.user.registered)."""
    deadline = time.monotonic() + timeout
    while True:
        found = dict(
            db.execute(select(Learner.user_id, Learner.user_type).where(Learner.user_id.in_(ids)))
            .tuples()
            .all()
        )
        if len(found) == len(ids):
            return found
        if time.monotonic() >= deadline:
            raise DemoLearnersMissing(
                f"Only {len(found)} of {len(ids)} demo learners have reached Learning. Run "
                "Identity's seed-demo-learners and pass the nonce it printed."
            )
        db.rollback()
        time.sleep(poll)


def _ease(question_id: str) -> float:
    """How often a question is got right first time, by default: 0.55 to 0.85."""
    return 0.55 + (zlib.crc32(question_id.encode()) % 300) / 1000


def _chance(
    question: deck.Question,
    number: int,
    title: str,
    topic: str,
    singaporean: bool,
    skill: float,
    versions_behind: int,
) -> tuple[float, str | None]:
    story = STORIES.get((title, number))
    chance, lure = story if story else (_ease(question.id or ""), None)
    if singaporean and (topic == "Singlish" or story):
        chance += 0.4
    elif singaporean:
        chance += 0.12
    if not story:
        chance -= 0.12 * versions_behind  # earlier versions were less clear
    return min(0.93, max(0.05, chance + skill)), lure


def _pick(
    rng: random.Random,
    the_deck: deck.Deck,
    question: deck.Question,
    chance: float,
    lure: str | None,
) -> tuple[str, bool]:
    right = the_deck.correct_option(question)
    if right is None or not the_deck.is_scored(question):
        return question.options[0].id or "", True
    if rng.random() < chance:
        return right.id or "", True
    wrong = [option for option in question.options if option.id != right.id]
    weights = [6 if option.text == lure else 1 for option in wrong]
    return rng.choices(wrong, weights)[0].id or "", False


def _moment(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """A time between start and end, more often recent, at a usual hour in Singapore."""
    span = (end - start).total_seconds()
    when = start + timedelta(seconds=span * rng.random() ** 0.7)
    local = (when + SINGAPORE).replace(hour=rng.choice(HOURS), minute=rng.randrange(60))
    when = local - SINGAPORE
    return min(max(when, start), end)


def demo_activity(
    db: Session,
    nonce: str,
    now: datetime | None = None,
    seed: int = 84,
    timeout: float = 60.0,
    count: int = DEFAULT_COUNT,
) -> list[str]:
    """Replace this run's demo learners' lesson runs. Returns a short log."""
    if count < 1:
        raise ValueError("count must be at least 1")
    now = now or datetime.now(UTC)
    rng = random.Random(seed)
    ids = demo_user_ids(nonce, count)
    kinds = wait_for_learners(db, ids, timeout)

    # Running again with the same nonce starts their history afresh.
    db.execute(delete(LessonAttempt).where(LessonAttempt.user_id.in_(ids)))
    db.execute(delete(LessonCompletion).where(LessonCompletion.user_id.in_(ids)))

    people = [(user_id, kinds[user_id] == SINGAPOREAN, rng.gauss(0, 0.08)) for user_id in ids]
    lessons = db.execute(
        visible_to_users(
            select(LearnableLesson, LearnableTopic.name, LearnableTopic.position)
            .join(LearnableTopic, LearnableLesson.topic_id == LearnableTopic.id)
            .where(lesson_visible())
            .order_by(LearnableTopic.position, LearnableLesson.position)
        )
    ).all()
    start = now - timedelta(weeks=WEEKS)
    runs = 0
    for index, (lesson, topic, topic_position) in enumerate(lessons):
        versions = list(
            db.scalars(
                select(LessonDeck)
                .where(LessonDeck.lesson_id == lesson.id)
                .order_by(LessonDeck.number)
            )
        )
        if not versions:
            continue
        # Earlier topics and lessons are taken by more learners.
        popularity = max(0.3, 0.8 - 0.06 * topic_position - 0.03 * (index % 3))
        for user_id, singaporean, skill in people:
            if rng.random() > popularity:
                continue
            first = _moment(rng, start, now)
            share = (first - start) / (now - start)
            slot = min(int(share * len(versions)), len(versions) - 1)
            runs += _runs_for(
                db,
                rng,
                user_id,
                lesson,
                topic,
                versions[slot],
                len(versions) - 1 - slot,
                singaporean,
                skill,
                first,
                now,
            )
    db.commit()
    return [
        f"runs for {len(people)} demo learners at {DOMAIN} (nonce {nonce})",
        f"{runs} runs through {len(lessons)} lessons",
    ]


def _runs_for(
    db: Session,
    rng: random.Random,
    user_id: uuid.UUID,
    lesson: LearnableLesson,
    topic: str,
    version: LessonDeck,
    versions_behind: int,
    singaporean: bool,
    skill: float,
    when: datetime,
    now: datetime,
) -> int:
    """One learner's runs through one version: maybe abandoned, maybe retaken."""
    the_deck = deck.of(version)
    questions = []
    number = 0
    for card in the_deck.doc.cards:
        if card.question is not None:
            number += 1
            questions.append((number, card.question))

    runs = 0
    best: tuple[float, LessonAttempt] | None = None
    first_finish: datetime | None = None
    boost = 0.0
    for _ in range(2):  # a first run, and at most one more
        abandon = rng.random() < 0.1
        attempt = LessonAttempt(
            user_id=user_id, lesson_id=lesson.id, version_id=version.id, started_at=when
        )
        db.add(attempt)
        db.flush()
        correct = scored = 0
        for position, (number, question) in enumerate(questions):
            if abandon and position >= max(1, len(questions) - 1):
                break
            chance, lure = _chance(
                question,
                number,
                lesson.display_title,
                topic,
                singaporean,
                skill + boost,
                versions_behind,
            )
            option_id, right = _pick(rng, the_deck, question, chance, lure)
            counts = the_deck.is_scored(question)
            db.add(
                AttemptAnswer(
                    attempt_id=attempt.id,
                    question_id=question.id,
                    option_id=option_id,
                    correct=right,
                    scored=counts,
                    answered_at=when + timedelta(seconds=25 * (position + 1)),
                )
            )
            if counts:
                scored += 1
                correct += right
        runs += 1
        if not abandon:
            attempt.finished_at = when + timedelta(seconds=25 * (len(questions) + 1))
            attempt.correct, attempt.scored = correct, scored
            share = correct / scored if scored else 1.0
            if best is None or share >= best[0]:
                best = (share, attempt)
            first_finish = first_finish or attempt.finished_at
        # Most who stop come back; some who got things wrong try again, and do better.
        again = abandon or (correct < scored and rng.random() < 0.6)
        when = when + timedelta(days=rng.randint(1, 6), hours=rng.randint(0, 5))
        if not again or when > now:
            break
        boost = 0.0 if abandon else 0.3

    if best is not None:
        _, attempt = best
        db.add(
            LessonCompletion(
                user_id=user_id,
                lesson_id=lesson.id,
                best_correct=attempt.correct or 0,
                best_scored=attempt.scored or 0,
                best_attempt_id=attempt.id,
                completed_at=first_finish,
                updated_at=attempt.finished_at,
            )
        )
    return runs
