"""Looking after the read models: emptying them for a rebuild, and waiting for them to fill.

Rebuild (detailed plan 3.2): `reset-read-models` empties every read model except
`erased_learners` (erasure is for good), then Content's `republish-catalog` and Identity's
`republish-learners` send the current state of everything again, and the ordinary consumer
path applies it. Republishing without a reset is also safe: every event carries the
aggregate's current version, which is at least the stored one.
"""

import time
from collections.abc import Callable

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, aliased

from app.models import (
    READ_MODELS,
    LearnableLesson,
    LearnableTopic,
    Learner,
    LessonDeck,
    QuizBank,
)
from app.seed import TOPICS, seed_learner_emails, user_id_for


def reset(db: Session) -> list[str]:
    """Empty the read models (never `erased_learners`). Returns the tables emptied."""
    tables = [model.__tablename__ for model in READ_MODELS]
    db.execute(text(f"TRUNCATE {', '.join(tables)}"))
    db.commit()
    return tables


def counts(db: Session) -> dict[str, int]:
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model)) or 0
        for model in READ_MODELS
    }


def missing(db: Session) -> list[str]:
    """What the seeds publish that has not reached the read models yet (empty when done)."""
    found: list[str] = []
    names = set(db.scalars(select(LearnableTopic.name).where(LearnableTopic.deleted.is_(False))))
    absent_topics = [name for name in TOPICS if name not in names]
    if absent_topics:
        found.append(f"topics {', '.join(absent_topics)}")
    if not db.scalar(select(func.count()).select_from(LearnableLesson)):
        found.append("published lessons")
    deck = aliased(LessonDeck)
    without_deck = db.scalar(
        select(func.count())
        .select_from(LearnableLesson)
        .where(~select(deck.id).where(deck.id == LearnableLesson.latest_version_id).exists())
    )
    if without_deck:
        found.append(f"the latest version of {without_deck} lesson(s)")
    bank = db.scalar(select(QuizBank))
    if bank is None:
        found.append("the aptitude bank")
    else:
        known = {str(topic_id) for topic_id in db.scalars(select(LearnableTopic.id))}
        if any(row["topic_id"] not in known for row in bank.topics):
            found.append("a topic the aptitude bank names")
    ids = {user_id_for(email): email for email in seed_learner_emails()}
    present = set(db.scalars(select(Learner.user_id).where(Learner.user_id.in_(ids))))
    absent_users = [email for user_id, email in ids.items() if user_id not in present]
    if absent_users:
        found.append(f"learners {', '.join(absent_users)}")
    return found


def wait(
    session_factory: Callable[[], Session],
    timeout: float,
    *,
    poll: float = 1.0,
    settle: int = 2,
    say: Callable[[str], None] = print,
) -> bool:
    """Block until nothing is `missing` and the read models have stopped changing for
    `settle` polls in a row (events still arriving would change the counts), or until
    `timeout` seconds pass. True when ready."""
    deadline = time.monotonic() + timeout
    previous: dict | None = None
    steady = 0
    last_report = ""
    while True:
        try:
            with session_factory() as db:
                gaps = missing(db)
                now = counts(db)
        except Exception as error:  # noqa: BLE001 - the database may still be starting
            gaps, now = [f"the database ({error.__class__.__name__})"], None
        steady = steady + 1 if not gaps and now == previous else 0
        previous = now
        if steady >= settle:
            say(f"Read models ready: {now}")
            return True
        report = "waiting for " + "; ".join(gaps) if gaps else "waiting for events to settle"
        if report != last_report:
            say(report)
            last_report = report
        if time.monotonic() >= deadline:
            say(f"Timed out: still {report.removeprefix('waiting for ')}.")
            return False
        time.sleep(poll)
