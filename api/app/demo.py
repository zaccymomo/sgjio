"""Demo learners and their lesson runs, so lesson insights (SCRUM-84) have something to show.

python -m app.cli demo-activity

- adds 60 demo learners (40 newcomers, 20 Singaporeans) with emails at demo.sgjio.example.com
  and a random password nobody knows, so they can never sign in.
- gives them runs through every published lesson over the last 12 weeks, ending today. A
  lesson's versions take turns: the first version is live first, the newest last.
- answers follow simple rules: each question has a difficulty, Singaporeans know Singlish,
  later versions are a little clearer, some learners stop half way, and some retake a
  lesson they got wrong and do better. A few questions are made confusing on purpose
  (STORIES), so the demo has something to find.
- running it again deletes the demo learners and everything they did, then adds them back
  with dates relative to today. Nobody else's data is touched.
"""

import random
import secrets
import zlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import lesson_doc
from app.lesson_doc import ChoiceQuestion, LessonDoc
from app.models import (
    AttemptAnswer,
    Lesson,
    LessonAttempt,
    LessonCompletion,
    LessonStatus,
    LessonVersion,
    Topic,
    User,
    UserRole,
    UserType,
)
from app.security import hash_password

DOMAIN = "demo.sgjio.example.com"
NEWCOMERS = 40
SINGAPOREANS = 20
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


def _ease(question_id: str) -> float:
    """How often a question is got right first time, by default: 0.55 to 0.85."""
    return 0.55 + (zlib.crc32(question_id.encode()) % 300) / 1000


def _chance(
    question: ChoiceQuestion,
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
    rng: random.Random, question: ChoiceQuestion, chance: float, lure: str | None
) -> tuple[str, bool]:
    right = lesson_doc.correct_option(question)
    if right is None or not lesson_doc.is_scored(question):
        return question.options[0].id or "", True
    if rng.random() < chance:
        return right.id or "", True
    wrong = [option for option in question.options if not option.correct]
    weights = [6 if option.text == lure else 1 for option in wrong]
    return rng.choices(wrong, weights)[0].id or "", False


def _moment(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """A time between start and end, more often recent, at a usual hour in Singapore."""
    span = (end - start).total_seconds()
    when = start + timedelta(seconds=span * rng.random() ** 0.7)
    local = (when + SINGAPORE).replace(hour=rng.choice(HOURS), minute=rng.randrange(60))
    when = local - SINGAPORE
    return min(max(when, start), end)


def _clear(db: Session) -> None:
    db.execute(delete(User).where(User.email.like(f"%@{DOMAIN}")))
    db.commit()


def demo_activity(db: Session, now: datetime | None = None, seed: int = 84) -> list[str]:
    """Replace the demo learners and their runs. Returns a short log."""
    now = now or datetime.now(UTC)
    rng = random.Random(seed)
    _clear(db)

    password = hash_password(secrets.token_urlsafe(24))
    people = []
    for n in range(1, NEWCOMERS + SINGAPOREANS + 1):
        singaporean = n > NEWCOMERS
        user = User(
            name=f"Demo learner {n:02}",
            email=f"learner{n:02}@{DOMAIN}",
            password_hash=password,
            role=UserRole.USER,
            user_type=UserType.SINGAPOREAN if singaporean else UserType.NEWCOMER,
        )
        db.add(user)
        people.append((user, singaporean, rng.gauss(0, 0.08)))
    db.flush()

    lessons = db.execute(
        select(Lesson, Topic.name, Topic.position)
        .join(Topic, Lesson.topic_id == Topic.id)
        .where(Lesson.status == LessonStatus.PUBLISHED, Topic.archived_at.is_(None))
        .order_by(Topic.position, Lesson.position)
    ).all()
    start = now - timedelta(weeks=WEEKS)
    runs = 0
    for index, (lesson, topic, topic_position) in enumerate(lessons):
        versions = list(
            db.scalars(
                select(LessonVersion)
                .where(LessonVersion.lesson_id == lesson.id)
                .order_by(LessonVersion.number)
            )
        )
        if not versions:
            continue
        # Earlier topics and lessons are taken by more learners.
        popularity = max(0.3, 0.8 - 0.06 * topic_position - 0.03 * (index % 3))
        for user, singaporean, skill in people:
            if rng.random() > popularity:
                continue
            first = _moment(rng, start, now)
            share = (first - start) / (now - start)
            slot = min(int(share * len(versions)), len(versions) - 1)
            version = versions[slot]
            runs += _runs_for(
                db,
                rng,
                user,
                lesson,
                topic,
                version,
                len(versions) - 1 - slot,
                singaporean,
                skill,
                first,
                now,
            )
    db.commit()
    return [
        f"{len(people)} demo learners at {DOMAIN}",
        f"{runs} runs through {len(lessons)} lessons",
    ]


def _runs_for(
    db: Session,
    rng: random.Random,
    user: User,
    lesson: Lesson,
    topic: str,
    version: LessonVersion,
    versions_behind: int,
    singaporean: bool,
    skill: float,
    when: datetime,
    now: datetime,
) -> int:
    """One learner's runs through one version: maybe abandoned, maybe retaken."""
    doc = LessonDoc.model_validate(version.doc)
    questions = []
    number = 0
    for card in doc.cards:
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
            user_id=user.id, lesson_id=lesson.id, version_id=version.id, started_at=when
        )
        db.add(attempt)
        db.flush()
        correct = scored = 0
        for position, (number, question) in enumerate(questions):
            if abandon and position >= max(1, len(questions) - 1):
                break
            chance, lure = _chance(
                question, number, lesson.title, topic, singaporean, skill + boost, versions_behind
            )
            option_id, right = _pick(rng, question, chance, lure)
            counts = lesson_doc.is_scored(question)
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
                user_id=user.id,
                lesson_id=lesson.id,
                best_correct=attempt.correct or 0,
                best_scored=attempt.scored or 0,
                best_attempt_id=attempt.id,
                completed_at=first_finish,
                updated_at=attempt.finished_at,
            )
        )
    return runs
