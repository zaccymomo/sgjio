"""The seed sets the order of what it creates, and never reorders anything (SCRUM-66), and
loads its lessons from content/ (SCRUM-77). It gives topics a description, but never
replaces one an administrator wrote (SCRUM-86)."""

import yaml
from sqlalchemy import select

from app.config import get_settings
from app.content_import import find_lesson_files
from app.models import AptitudeAttempt, Lesson, LessonStatus, Topic, User
from app.seed import TEST_USERS, TOPICS, seed


def _lesson_files() -> list[dict]:
    """Every lesson file in content/, in folder order."""
    root = get_settings().content_dir
    return [yaml.safe_load(path.read_text()) for path in find_lesson_files(root)]


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
    assert _topic_order(db) == list(TOPICS)
    for name in TOPICS:
        assert _lesson_order(db, name) == [
            f["title"] for f in _lesson_files() if f.get("topic") == name
        ]


def test_the_seed_publishes_the_lessons_in_content(db):
    seed(db)

    files = _lesson_files()
    published = [f["title"] for f in files if f.get("publish", True)]
    drafts = [f["title"] for f in files if not f.get("publish", True)]
    assert sorted(
        db.scalars(select(Lesson.title).where(Lesson.status == LessonStatus.PUBLISHED))
    ) == sorted(published)
    assert sorted(
        db.scalars(select(Lesson.title).where(Lesson.status == LessonStatus.DRAFT))
    ) == sorted(drafts)
    assert len(published) >= 12  # SCRUM-77 AC1: at least 4 topics with 3 lessons each


def test_seeded_topics_have_multiple_lesson_levels(db):
    seed(db)
    for topic in db.scalars(select(Topic)):
        levels = set(db.scalars(select(Lesson.level).where(Lesson.topic_id == topic.id)))
        assert len(levels) > 1


def test_seeded_level_users_and_skipped_user_are_ready_to_demo(db):
    seed(db)
    for email, (_, expected_level) in TEST_USERS.items():
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.current_level == (expected_level or 1)
        attempts = list(
            db.scalars(select(AptitudeAttempt).where(AptitudeAttempt.user_id == user.id))
        )
        assert len(attempts) == (0 if expected_level is None else 1)


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


def test_a_fresh_seed_gives_every_topic_its_description(db):
    seed(db)
    descriptions = dict(db.execute(select(Topic.name, Topic.description)).all())
    assert descriptions == TOPICS
    assert all(0 < len(description) <= 200 for description in TOPICS.values())


def test_reseeding_fills_an_empty_description_but_keeps_an_edited_one(db):
    seed(db)
    singlish = db.scalar(select(Topic).where(Topic.name == "Singlish"))
    festivals = db.scalar(select(Topic).where(Topic.name == "Festivals"))
    singlish.description = "Written by an administrator."
    festivals.description = ""
    db.commit()

    assert seed(db) == ["description for topic Festivals"]

    db.expire_all()
    assert singlish.description == "Written by an administrator."
    assert festivals.description == TOPICS["Festivals"]
