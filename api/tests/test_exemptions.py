"""SCRUM-113: per-topic exemptions replace the single user level in the schema.

Each user has at most one completed aptitude quiz and, from it, one exemption level (0 to
5) per topic. Exempted lessons are worked out from that and each lesson's level.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db import engine
from app.exemptions import exempted_lessons, exemption_levels, is_exempted
from app.models import (
    AptitudeAttempt,
    Lesson,
    LessonStatus,
    Topic,
    TopicExemption,
    User,
)

API_DIR = Path(__file__).resolve().parent.parent


def _config() -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    return config


def _topic(db, name: str = "Hawker culture", position: int = 0) -> Topic:
    topic = Topic(name=name, position=position)
    db.add(topic)
    db.commit()
    return topic


def _lesson(db, topic: Topic, title: str, level: int, published: bool = True) -> Lesson:
    lesson = Lesson(
        title=title,
        topic=topic,
        level=level,
        status=LessonStatus.PUBLISHED if published else LessonStatus.DRAFT,
        published_at=datetime.now(UTC) if published else None,
    )
    db.add(lesson)
    db.commit()
    return lesson


def _quiz(db, user: User, exemptions: dict[Topic, int] | None = None) -> AptitudeAttempt:
    """A completed quiz and its exemptions, saved together as SCRUM-99 AC7 will."""
    attempt = AptitudeAttempt(user_id=user.id, results=[{"correct": True}])
    db.add(attempt)
    db.flush()
    for topic, level in (exemptions or {}).items():
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=level))
    db.commit()
    return attempt


# --- AC1: the exemption table exists and the user level is gone --------------------------


def test_the_exemption_table_exists_and_users_have_no_level():
    schema = inspect(engine)
    assert "level" not in {c["name"] for c in schema.get_columns("users")}
    assert "level" not in {c["name"] for c in schema.get_columns("aptitude_attempts")}
    assert {c["name"] for c in schema.get_columns("topic_exemptions")} == {
        "user_id",
        "topic_id",
        "level",
    }
    referred = {
        (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in schema.get_foreign_keys("topic_exemptions")
    }
    assert referred == {
        (("user_id",), "users"),
        (("user_id",), "aptitude_attempts"),
        (("topic_id",), "topics"),
    }
    assert schema.get_pk_constraint("topic_exemptions")["constrained_columns"] == [
        "user_id",
        "topic_id",
    ]


# --- AC2: one exemption per topic, one completed quiz per user ---------------------------


def test_a_user_has_at_most_one_exemption_per_topic(db, make_user):
    user = make_user()
    topic = _topic(db)
    _quiz(db, user, {topic: 2})
    with pytest.raises(IntegrityError):
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=3))
        db.commit()


def test_a_user_can_be_exempted_in_several_topics(db, make_user):
    user = make_user()
    singlish = _topic(db, "Singlish", position=0)
    hawker = _topic(db, "Hawker culture", position=1)
    _quiz(db, user, {singlish: 0, hawker: 4})
    assert exemption_levels(db, user.id) == {singlish.id: 0, hawker.id: 4}


def test_a_user_has_at_most_one_completed_quiz(db, make_user):
    user = make_user()
    _quiz(db, user)
    with pytest.raises(IntegrityError):
        db.add(AptitudeAttempt(user_id=user.id, results=[]))
        db.commit()


def test_exemptions_cannot_exist_without_a_completed_quiz(db, make_user):
    user = make_user()
    topic = _topic(db)
    with pytest.raises(IntegrityError):
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=1))
        db.commit()


def test_another_users_exemptions_are_not_theirs(db, make_user):
    user = make_user()
    other = make_user(email="other@example.com")
    topic = _topic(db)
    _quiz(db, other, {topic: 3})
    assert exemption_levels(db, user.id) == {}


def test_deleting_an_account_deletes_its_quiz_and_exemptions(db, make_user):
    user = make_user()
    topic = _topic(db)
    _quiz(db, user, {topic: 2})
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    assert db.scalar(select(AptitudeAttempt)) is None
    assert db.scalar(select(TopicExemption)) is None


# --- AC3: an exemption level outside 0 to 5 is rejected ----------------------------------


@pytest.mark.parametrize("level", [None, -1, 6])
def test_an_exemption_outside_0_to_5_is_rejected(db, make_user, level):
    user = make_user()
    topic = _topic(db)
    _quiz(db, user)
    with pytest.raises(IntegrityError):
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=level))
        db.commit()


@pytest.mark.parametrize("level", [0, 5])
def test_exemptions_of_0_and_5_are_accepted(db, make_user, level):
    user = make_user()
    topic = _topic(db)
    _quiz(db, user, {topic: level})
    assert exemption_levels(db, user.id) == {topic.id: level}


# --- AC5: exempted lessons are worked out, not stored ------------------------------------


def test_exempted_lessons_come_from_the_topic_exemption_and_lesson_levels(db, make_user):
    user = make_user()
    singlish = _topic(db, "Singlish", position=0)
    hawker = _topic(db, "Hawker culture", position=1)
    level_1 = _lesson(db, singlish, "Singlish 1", level=1)
    level_2 = _lesson(db, singlish, "Singlish 2", level=2)
    _lesson(db, singlish, "Singlish 3", level=3)
    _lesson(db, singlish, "Singlish 1 draft", level=1, published=False)
    _lesson(db, hawker, "Hawker 1", level=1)
    _quiz(db, user, {singlish: 2, hawker: 0})

    assert set(db.scalars(exempted_lessons(user.id))) == {level_1.id, level_2.id}

    # A lesson published later at an exempted level is exempted too (SCRUM-104 AC3).
    later = _lesson(db, singlish, "Singlish 2, later", level=2)
    assert later.id in set(db.scalars(exempted_lessons(user.id)))

    exempt = dict(
        db.execute(select(Lesson.title, is_exempted(user.id)).order_by(Lesson.title)).all()
    )
    assert exempt["Singlish 3"] is False
    assert exempt["Hawker 1"] is False


def test_a_user_who_skipped_the_quiz_is_exempted_from_nothing(db, make_user):
    user = make_user()
    topic = _topic(db)
    _lesson(db, topic, "Level 1", level=1)
    assert exemption_levels(db, user.id) == {}
    assert list(db.scalars(exempted_lessons(user.id))) == []


# --- AC4 and AC6: the migration keeps completions and answers, and rolls back -------------


def _schema() -> dict:
    """Every table's columns, constraints and indexes, to compare before and after."""
    schema = inspect(engine)
    return {
        table: {
            "columns": sorted(
                (c["name"], str(c["type"]), c["nullable"]) for c in schema.get_columns(table)
            ),
            "pk": schema.get_pk_constraint(table)["constrained_columns"],
            "fks": sorted(fk["name"] for fk in schema.get_foreign_keys(table)),
            "uniques": sorted(u["name"] for u in schema.get_unique_constraints(table)),
            "checks": sorted(c["name"] for c in schema.get_check_constraints(table)),
            "indexes": sorted(i["name"] for i in schema.get_indexes(table)),
        }
        for table in schema.get_table_names()
    }


def test_the_migration_removes_levels_but_keeps_completions_and_answers():
    config = _config()
    try:
        command.downgrade(config, "0015")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, name, email, role, level) VALUES "
                    "('00000000-0000-0000-0000-000000000001', 'Q', 'q@example.com', 'user', 3)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO lessons (id, title, status, level, position) VALUES "
                    "('00000000-0000-0000-0000-000000000002', 'Kopi', 'published', 1, 0)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO lesson_completions (id, user_id, lesson_id, best_correct,"
                    " best_scored) VALUES (gen_random_uuid(),"
                    " '00000000-0000-0000-0000-000000000001',"
                    " '00000000-0000-0000-0000-000000000002', 2, 3)"
                )
            )
            # Two quizzes from the old retake design: the latest is kept.
            conn.execute(
                text(
                    "INSERT INTO aptitude_attempts (id, user_id, taken_at, level, results) VALUES"
                    " (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',"
                    " '2026-10-30T10:00:00+00', 2, '[{\"correct\": false}]'),"
                    " (gen_random_uuid(), '00000000-0000-0000-0000-000000000001',"
                    " '2026-10-31T10:00:00+00', 3, '[{\"correct\": true}]')"
                )
            )
        command.upgrade(config, "head")

        with engine.connect() as conn:
            completion = conn.execute(
                text("SELECT best_correct, best_scored FROM lesson_completions")
            ).one()
            quiz = conn.execute(text("SELECT taken_at, results FROM aptitude_attempts")).one()
            user = conn.execute(text("SELECT email FROM users")).one()
        assert tuple(completion) == (2, 3)
        assert quiz.results == [{"correct": True}]
        assert quiz.taken_at == datetime(2026, 10, 31, 10, tzinfo=UTC)
        assert user.email == "q@example.com"
    finally:
        command.upgrade(config, "head")


def test_rolling_back_returns_the_schema_to_its_previous_state():
    config = _config()
    try:
        command.downgrade(config, "0015")
        before = _schema()
        command.upgrade(config, "head")
        assert "topic_exemptions" in _schema()
        command.downgrade(config, "0015")
        assert _schema() == before
        assert "topic_exemptions" not in before
    finally:
        command.upgrade(config, "head")
