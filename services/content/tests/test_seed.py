"""The seed sets the order of what it creates, and never reorders anything (SCRUM-66), and
loads its lessons from content/ (SCRUM-77). It gives topics a description, but never
replaces one an administrator wrote (SCRUM-86). Content's part of the monolith's
test_seed.py and test_health_and_schema.py; users and their results are other services'."""

from datetime import UTC, datetime

import pytest
import yaml
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.content_import import find_lesson_files
from app.lesson_doc import LessonDoc, correct_option
from app.models import AptitudeQuestion, Lesson, LessonStatus, LessonVersion, Topic
from app.seed import TOPICS, seed
from tests.conftest import event_types, outbox_events


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


def test_seeded_question_bank_covers_every_topic_and_level(db):
    seed(db)
    for topic in db.scalars(select(Topic)):
        levels = set(
            db.scalars(
                select(AptitudeQuestion.level).where(
                    AptitudeQuestion.topic_id == topic.id,
                    AptitudeQuestion.is_active.is_(True),
                )
            )
        )
        assert levels == {1, 2, 3, 4, 5}


def test_seed_creates_topics_and_published_lessons_with_one_version(db):
    created = seed(db)
    assert created, "first run should create data"
    assert sorted(t.name for t in db.scalars(select(Topic))) == sorted(TOPICS)
    lesson = db.scalar(select(Lesson).where(Lesson.status == LessonStatus.PUBLISHED))
    doc = LessonDoc.model_validate(lesson.draft)
    questions = [card.question for card in doc.cards if card.question]
    assert questions
    assert all(correct_option(question) is not None for question in questions)
    assert [version.number for version in lesson.versions] == [1]


def test_seeding_again_changes_nothing(db):
    seed(db)
    before = {
        "topics": list(db.execute(select(Topic.id, Topic.position)).all()),
        "lessons": list(db.execute(select(Lesson.id, Lesson.position)).all()),
    }
    sent = len(outbox_events())

    assert seed(db) == []  # nothing created
    db.expire_all()
    assert set(db.execute(select(Topic.id, Topic.position)).all()) == set(before["topics"])
    assert set(db.execute(select(Lesson.id, Lesson.position)).all()) == set(before["lessons"])
    assert db.scalar(select(func.count()).select_from(Topic)) == len(TOPICS)
    assert outbox_events(since=sent) == []  # and announces nothing


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
    for question in db.scalars(
        select(AptitudeQuestion).where(AptitudeQuestion.topic_id == getting_around.id)
    ):
        db.delete(question)
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
    sent = len(outbox_events())

    assert seed(db) == ["description for topic Festivals"]

    db.expire_all()
    assert singlish.description == "Written by an administrator."
    assert festivals.description == TOPICS["Festivals"]
    [event] = outbox_events(since=sent)
    assert event["type"] == "content.topic.changed"
    assert event["data"]["description"] == TOPICS["Festivals"]


def test_reseeding_reports_a_published_lesson_keeping_its_level(db):
    """SCRUM-103: a published lesson's level is fixed, so a file that now says another
    level is reported rather than applied or silently ignored."""
    seed(db)
    lesson = db.scalar(
        select(Lesson).where(Lesson.key.is_not(None), Lesson.status == LessonStatus.PUBLISHED)
    )
    file_level = lesson.level
    lesson.level = 5 if file_level != 5 else 4
    db.commit()

    log = seed(db)

    assert any(lesson.key in line and "level not changed" in line for line in log)
    db.expire_all()
    assert db.get(Lesson, lesson.id).level != file_level


# --- Natural keys and events (contracts/README.md) -------------------------------


def test_seeded_data_carries_its_natural_keys(db):
    seed(db)
    keys = {e["data"]["key"] for e in outbox_events("content.lesson.changed")}
    assert keys == set(db.scalars(select(Lesson.key).where(Lesson.version > 0)))
    seed_keys = {e["data"]["seed_key"] for e in outbox_events("content.aptitude_question.changed")}
    assert None not in seed_keys
    assert seed_keys == set(db.scalars(select(AptitudeQuestion.seed_key)))
    names = {e["data"]["name"] for e in outbox_events("content.topic.changed")}
    assert names == set(TOPICS)


def test_the_seed_announces_everything_learning_needs(db):
    seed(db)
    types = event_types()
    lessons = db.scalar(select(func.count()).select_from(Lesson).where(Lesson.version > 0))
    questions = db.scalar(select(func.count()).select_from(AptitudeQuestion))
    assert types.count("content.topic.changed") == len(TOPICS)
    assert types.count("content.lesson_version.published") == lessons
    assert types.count("content.lesson.changed") == lessons
    assert types.count("content.aptitude_question.changed") == questions
    assert types.count("content.aptitude_bank.changed") == 1
    [bank] = outbox_events("content.aptitude_bank.changed")
    assert bank["data"]["ready"] is True
    assert bank["correlation_id"] is None  # not caused by a request


# --- Schema ---------------------------------------------------------------------------------


def test_topic_names_are_unique_ignoring_case(db):
    db.add(Topic(name="Singlish"))
    db.commit()
    db.add(Topic(name="singlish"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_a_lesson_has_each_version_number_once(db):
    lesson = Lesson(title="Test")
    now = datetime.now(UTC)
    lesson.versions = [
        LessonVersion(number=1, title="Test", doc={"cards": []}, published_at=now),
        LessonVersion(number=1, title="Test", doc={"cards": []}, published_at=now),
    ]
    db.add(lesson)
    with pytest.raises(IntegrityError):
        db.commit()


def test_database_rejects_unknown_lesson_status(db):
    # Raw SQL on purpose: this checks the database's own CHECK constraint, not Python.
    lesson = Lesson(title="Test")
    db.add(lesson)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE lessons SET status = 'archived' WHERE id = :id"), {"id": lesson.id})
        db.commit()


def test_an_aptitude_questions_correct_option_must_be_one_of_its_options(db):
    topic = Topic(name="Singlish")
    db.add(topic)
    db.commit()
    db.add(
        AptitudeQuestion(
            topic_id=topic.id,
            level=1,
            prompt="?",
            options=[{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
            correct_option_id="z",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
