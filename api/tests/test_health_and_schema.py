"""SCRUM-72: the schema and seed data."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Lesson, LessonVersion, Topic, User
from app.seed import TOPICS, seed


def test_health_reports_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_seed_creates_admin_user_topics_and_sample_lesson(db):
    created = seed(db)
    assert created, "first run should create data"
    assert db.scalar(select(func.count()).select_from(User)) == 2
    assert sorted(t.name for t in db.scalars(select(Topic))) == sorted(TOPICS)
    lesson = db.scalar(select(Lesson))
    questions = [card["question"] for card in lesson.draft["cards"] if card["question"]]
    assert questions
    assert all(sum(o["correct"] for o in q["options"]) == 1 for q in questions)
    assert [version.number for version in lesson.versions] == [1]


def test_seed_is_safe_to_run_twice(db):
    seed(db)
    assert seed(db) == []
    assert db.scalar(select(func.count()).select_from(Topic)) == len(TOPICS)


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
