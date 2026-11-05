"""SCRUM-110: lesson and aptitude question levels and the aptitude quiz in the schema.

Lessons and aptitude questions share one scale of Level 1 to 5 (Epic 6). The single user
level SCRUM-110 added was replaced by per-topic exemptions in SCRUM-113
(`test_exemptions.py`), so every user now sees lessons at every level.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.aptitude import has_taken_quiz, quiz_attempt
from app.db import engine
from app.models import (
    AptitudeAttempt,
    AptitudeQuestion,
    Lesson,
    LessonCompletion,
    LessonStatus,
    LessonVersion,
    Topic,
    User,
)

API_DIR = Path(__file__).resolve().parent.parent
USER = {"email": "user@example.com", "password": "Password123"}

DOC = {
    "cards": [
        {
            "id": "c1",
            "text": "Pick {{blank}}.",
            "question": {
                "id": "q1",
                "options": [
                    {"id": "right", "text": "Right", "correct": True},
                    {"id": "wrong", "text": "Wrong"},
                ],
                "explanation": "Because.",
            },
        }
    ]
}
OPTIONS = [{"id": "a", "text": "Chope"}, {"id": "b", "text": "Queue"}]


def _config() -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    return config


def _topic(db, name: str = "Hawker culture", position: int = 0) -> Topic:
    topic = Topic(name=name, position=position)
    db.add(topic)
    db.commit()
    return topic


def _lesson(db, topic: Topic, title: str, level: int = 1, position: int = 0) -> Lesson:
    now = datetime.now(UTC)
    lesson = Lesson(
        title=title,
        topic=topic,
        level=level,
        position=position,
        status=LessonStatus.PUBLISHED,
        published_at=now,
        draft=DOC,
    )
    db.add(lesson)
    db.flush()
    db.add(
        LessonVersion(
            lesson_id=lesson.id, number=1, title=title, summary="", doc=DOC, published_at=now
        )
    )
    db.commit()
    return lesson


def _complete(db, user: User, lesson: Lesson) -> None:
    db.add(LessonCompletion(user_id=user.id, lesson_id=lesson.id, best_correct=1, best_scored=1))
    db.commit()


def _sign_in(client, make_user) -> User:
    user = make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    return user


def _question(db, topic: Topic, level: int = 1, **overrides) -> AptitudeQuestion:
    fields = {
        "topic_id": topic.id,
        "level": level,
        "prompt": "What does 'chope' mean?",
        "options": OPTIONS,
        "correct_option_id": "a",
    } | overrides
    question = AptitudeQuestion(**fields)
    db.add(question)
    db.commit()
    return question


# --- AC1: the tables and fields exist ---------------------------------------------------


def test_the_new_tables_and_fields_exist():
    schema = inspect(engine)
    assert "level" in {c["name"] for c in schema.get_columns("lessons")}
    users = {c["name"] for c in schema.get_columns("users")}
    assert "intro_finished_at" in users
    # Quizzes live in their own table since 0014; users have no level since 0016.
    assert not {"quiz_results", "quiz_taken_at", "level"} & users
    quiz_attempts = {c["name"] for c in schema.get_columns("aptitude_attempts")}
    assert {"user_id", "taken_at", "results"} <= quiz_attempts
    [attempt_fk] = schema.get_foreign_keys("aptitude_attempts")
    assert attempt_fk["referred_table"] == "users"
    questions = {c["name"] for c in schema.get_columns("aptitude_questions")}
    assert {
        "topic_id",
        "level",
        "prompt",
        "options",
        "correct_option_id",
        "is_active",
    } <= questions
    [fk] = schema.get_foreign_keys("aptitude_questions")
    assert fk["referred_table"] == "topics"


def test_a_new_lesson_starts_at_level_1(db):
    lesson = Lesson(title="Ordering kopi")
    db.add(lesson)
    db.commit()
    assert lesson.level == 1


# --- AC3: a lesson or question without a valid level is refused --------------------------


@pytest.mark.parametrize("level", ["NULL", "0", "6"])
def test_a_lesson_without_a_valid_level_is_refused(level):
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO lessons (id, title, status, level) "
                f"VALUES (gen_random_uuid(), 'X', 'draft', {level})"
            )
        )


@pytest.mark.parametrize("level", [None, 0, 6])
def test_a_question_without_a_valid_level_is_refused(db, level):
    topic = _topic(db)
    with pytest.raises(IntegrityError):
        _question(db, topic, level=level)


def test_a_question_without_a_topic_is_refused(db):
    with pytest.raises(IntegrityError):
        db.add(AptitudeQuestion(level=1, prompt="?", options=OPTIONS, correct_option_id="a"))
        db.commit()


def test_the_correct_option_must_be_one_of_the_options(db):
    topic = _topic(db)
    with pytest.raises(IntegrityError):
        _question(db, topic, correct_option_id="z")


def _attempt(db, user: User, results: list):
    attempt = AptitudeAttempt(user_id=user.id, results=results)
    db.add(attempt)
    db.commit()
    return attempt


def test_a_quizs_results_must_be_a_list(db, make_user):
    user = make_user()
    with pytest.raises(IntegrityError):
        _attempt(db, user, results={"not": "a list"})


def test_a_user_who_skipped_the_quiz_has_no_attempt(db, make_user):
    user = make_user()
    assert quiz_attempt(db, user.id) is None
    assert not has_taken_quiz(db, user.id)


def test_another_users_quiz_is_not_theirs(db, make_user):
    user = make_user()
    other = make_user(email="other@example.com")
    _attempt(db, other, results=[])
    assert quiz_attempt(db, user.id) is None
    assert has_taken_quiz(db, other.id)


# --- AC5: each quiz keeps its own copy of the questions ------------------------------------


def test_editing_or_deactivating_a_question_leaves_past_results_alone(db, make_user):
    topic = _topic(db)
    question = _question(db, topic)
    answer = {
        "question_id": str(question.id),
        "topic_id": str(topic.id),
        "level": 1,
        "prompt": question.prompt,
        "chosen_option_id": "a",
        "correct": True,
    }
    user = make_user()
    attempt = _attempt(db, user, results=[answer])

    question.prompt = "Reworded"
    question.options = [{"id": "c", "text": "New"}, {"id": "d", "text": "Other"}]
    question.correct_option_id = "c"
    question.is_active = False
    db.commit()

    db.expire_all()
    assert db.get(AptitudeAttempt, attempt.id).results == [answer]


def test_deleting_an_account_deletes_its_quizzes(db, make_user):
    user = make_user()
    _attempt(db, user, results=[])
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    assert db.scalar(select(AptitudeAttempt)) is None


# --- SCRUM-104 AC4: lessons are no longer hidden by level --------------------------------


def test_a_user_sees_lessons_at_every_level(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db)
    done = _lesson(db, topic, "Level 1", level=1, position=0)
    _lesson(db, topic, "Level 3", level=3, position=1)
    _lesson(db, topic, "Level 5", level=5, position=2)
    _complete(db, user, done)

    body = client.get(f"/api/topics/{topic.id}").json()
    assert [lesson["title"] for lesson in body["lessons"]] == ["Level 1", "Level 3", "Level 5"]
    assert (body["completed"], body["available"]) == (1, 3)

    progress = client.get("/api/progress").json()
    assert (progress["completed"], progress["available"]) == (1, 3)
    assert progress["suggestion"]["title"] == "Level 3"


# --- AC2 and AC7: the migration fills in Level 1 and rolls back cleanly -------------------


def test_the_migration_puts_existing_lessons_at_level_1_and_rolls_back():
    config = _config()
    try:
        command.downgrade(config, "0012")
        tables = inspect(engine).get_table_names()
        assert "aptitude_questions" not in tables
        assert "level" not in {c["name"] for c in inspect(engine).get_columns("lessons")}
        assert "level" not in {c["name"] for c in inspect(engine).get_columns("users")}

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO lessons (id, title, summary, position, status) VALUES "
                    "(gen_random_uuid(), 'Old lesson', 'Kept as it was', 3, 'published')"
                )
            )
        command.upgrade(config, "head")

        with engine.connect() as conn:
            row = conn.execute(text("SELECT title, summary, position, level FROM lessons")).one()
        assert tuple(row) == ("Old lesson", "Kept as it was", 3, 1)
    finally:
        command.upgrade(config, "head")


def test_0014_moves_a_saved_quiz_into_attempts_and_rolls_back():
    config = _config()
    try:
        command.downgrade(config, "0013")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, name, email, role, level, quiz_results, quiz_taken_at)"
                    " VALUES (gen_random_uuid(), 'Q', 'q@example.com', 'user', 3,"
                    " '[{\"correct\": true}]', '2026-10-30T10:00:00+00')"
                )
            )
        command.upgrade(config, "0014")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT level, results, taken_at FROM aptitude_attempts")).one()
        assert row.level == 3
        assert row.results == [{"correct": True}]
        assert row.taken_at == datetime(2026, 10, 30, 10, tzinfo=UTC)

        # Rolling back puts the latest quiz back on the user.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO aptitude_attempts (id, user_id, taken_at, level, results) "
                    "SELECT gen_random_uuid(), id, '2026-10-31T10:00:00+00', 4, "
                    "'[{\"correct\": false}]' FROM users WHERE email = 'q@example.com'"
                )
            )
        command.downgrade(config, "0013")
        with engine.connect() as conn:
            back = conn.execute(
                text("SELECT quiz_results, quiz_taken_at FROM users WHERE email = 'q@example.com'")
            ).one()
        assert back.quiz_results == [{"correct": False}]
        assert back.quiz_taken_at == datetime(2026, 10, 31, 10, tzinfo=UTC)
    finally:
        command.upgrade(config, "head")
