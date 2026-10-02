"""The seed sets the order of what it creates, and never reorders anything (SCRUM-66)."""

from sqlalchemy import select

from app.models import Lesson, Topic
from app.seed import LESSONS, TOPICS, seed


def _topic_order(db) -> list[str]:
    return list(db.scalars(select(Topic.name).order_by(Topic.position, Topic.created_at)))


def _lesson_order(db, topic_name: str) -> list[str]:
    return list(
        db.scalars(
            select(Lesson.title)
            .join(Topic)
            .where(Topic.name == topic_name)
            .order_by(Lesson.position, Lesson.created_at)
        )
    )


def test_a_fresh_seed_uses_the_figma_order(db):
    seed(db)
    assert _topic_order(db) == TOPICS
    for name in TOPICS:
        assert _lesson_order(db, name) == [s["title"] for s in LESSONS if s["topic"] == name]


def test_seeding_again_changes_nothing(db):
    seed(db)
    before = {
        "topics": list(db.execute(select(Topic.id, Topic.position)).all()),
        "lessons": list(db.execute(select(Lesson.id, Lesson.position)).all()),
    }

    assert seed(db) == []  # nothing created
    db.expire_all()
    assert set(db.execute(select(Topic.id, Topic.position)).all()) == set(before["topics"])
    assert set(db.execute(select(Lesson.id, Lesson.position)).all()) == set(before["lessons"])


def test_reseeding_keeps_an_order_an_administrator_set(db):
    seed(db)
    topics = db.scalars(select(Topic).order_by(Topic.position)).all()
    for position, topic in enumerate(reversed(topics)):
        topic.position = position
    db.commit()

    seed(db)

    db.expire_all()
    assert _topic_order(db) == list(reversed(TOPICS))


def test_a_missing_topic_is_added_at_the_end(db):
    seed(db)
    getting_around = db.scalar(select(Topic).where(Topic.name == "Getting Around"))
    for lesson in getting_around.lessons:
        db.delete(lesson)
    db.delete(getting_around)
    db.commit()
    # An administrator moves the last remaining topic to the front.
    workplace = db.scalar(select(Topic).where(Topic.name == "Workplace"))
    workplace.position = -1
    db.commit()

    seed(db)

    db.expire_all()
    order = _topic_order(db)
    assert order[0] == "Workplace"
    assert order[-1] == "Getting Around"
