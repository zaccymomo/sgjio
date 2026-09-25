"""SCRUM-72: the schema and seed data."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Lesson, QuizOption, QuizQuestion, Topic, User
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
    assert lesson.question is not None
    assert sum(o.is_correct for o in lesson.question.options) == 1


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


def test_a_question_can_only_have_one_correct_option(db):
    lesson = Lesson(title="Test")
    lesson.question = QuizQuestion(
        prompt="?",
        options=[QuizOption(text="A", is_correct=True), QuizOption(text="B", is_correct=True)],
    )
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
