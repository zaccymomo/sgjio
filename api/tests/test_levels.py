"""SCRUM-110: levels and the aptitude quiz in the schema, and SCRUM-16's counting rule with
levels: each user sees the lessons at their level plus every lesson they have completed.

Users, lessons and aptitude questions share one scale of Level 1 to 5 (Epic 6).
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.aptitude import attempts, latest_attempt
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


def _sign_in(client, make_user, level: int | None = None) -> User:
    user = make_user(**USER)
    if level is not None:
        user.level = level
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
    assert {"level", "intro_finished_at"} <= users
    # Quizzes live in their own table since 0014, so every one is kept.
    assert not {"quiz_results", "quiz_taken_at"} & users
    quiz_attempts = {c["name"] for c in schema.get_columns("aptitude_attempts")}
    assert {"user_id", "taken_at", "level", "results"} <= quiz_attempts
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


def test_a_user_who_has_not_taken_the_quiz_counts_as_level_1(make_user):
    user = make_user()
    assert user.level is None
    assert user.current_level == 1


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


def test_a_users_level_must_be_1_to_5(db, make_user):
    user = make_user()
    user.level = 6
    with pytest.raises(IntegrityError):
        db.merge(user)
        db.commit()


def _attempt(db, user: User, level: int, results: list, taken_at: datetime | None = None):
    attempt = AptitudeAttempt(
        user_id=user.id, level=level, results=results, taken_at=taken_at or datetime.now(UTC)
    )
    db.add(attempt)
    db.commit()
    return attempt


@pytest.mark.parametrize("level", [None, 0, 6])
def test_a_quiz_without_a_valid_level_is_refused(db, make_user, level):
    user = make_user()
    with pytest.raises(IntegrityError):
        _attempt(db, user, level=level, results=[])


def test_a_quizs_results_must_be_a_list(db, make_user):
    user = make_user()
    with pytest.raises(IntegrityError):
        _attempt(db, user, level=1, results={"not": "a list"})


def test_a_user_who_skipped_the_quiz_has_no_attempts_and_is_level_1(db, make_user):
    user = make_user()
    assert latest_attempt(db, user.id) is None
    assert attempts(db, user.id) == []
    assert user.current_level == 1


# --- AC4 and AC5: every quiz is kept, the newest is the latest, each keeps its own copy ---


def test_a_retake_keeps_earlier_quizzes_and_becomes_the_latest(db, make_user):
    user = make_user()
    now = datetime.now(UTC)
    first = _attempt(
        db, user, level=1, results=[{"correct": False}], taken_at=now - timedelta(days=3)
    )
    second = _attempt(db, user, level=3, results=[{"correct": True}], taken_at=now)

    assert latest_attempt(db, user.id).id == second.id
    assert [a.id for a in attempts(db, user.id)] == [second.id, first.id]
    assert db.get(AptitudeAttempt, first.id).results == [{"correct": False}]


def test_another_users_quizzes_are_not_theirs(db, make_user):
    user = make_user()
    other = make_user(email="other@example.com")
    _attempt(db, other, level=4, results=[])
    assert latest_attempt(db, user.id) is None


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
    attempt = _attempt(db, user, level=1, results=[answer])

    question.prompt = "Reworded"
    question.options = [{"id": "c", "text": "New"}, {"id": "d", "text": "Other"}]
    question.correct_option_id = "c"
    question.is_active = False
    db.commit()

    db.expire_all()
    assert db.get(AptitudeAttempt, attempt.id).results == [answer]


def test_deleting_an_account_deletes_its_quizzes(db, make_user):
    user = make_user()
    _attempt(db, user, level=2, results=[])
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    assert db.scalar(select(AptitudeAttempt)) is None


# --- AC6 and SCRUM-16: lessons at your level, plus every one you completed -----------------


def test_a_user_sees_only_lessons_at_their_level(client, db, make_user):
    _sign_in(client, make_user, level=3)
    topic = _topic(db)
    _lesson(db, topic, "Level 1", level=1, position=0)
    _lesson(db, topic, "Level 3", level=3, position=1)
    _lesson(db, topic, "Level 5", level=5, position=2)

    body = client.get(f"/api/topics/{topic.id}").json()
    assert [lesson["title"] for lesson in body["lessons"]] == ["Level 3"]
    assert (body["completed"], body["available"]) == (0, 1)

    progress = client.get("/api/progress").json()
    assert (progress["topics"][0]["completed"], progress["topics"][0]["available"]) == (0, 1)
    assert progress["suggestion"]["title"] == "Level 3"


def test_completed_lessons_stay_listed_after_the_level_changes(client, db, make_user):
    user = _sign_in(client, make_user, level=1)
    topic = _topic(db)
    done = _lesson(db, topic, "Done at Level 1", level=1, position=0)
    _lesson(db, topic, "Not done at Level 1", level=1, position=1)
    _lesson(db, topic, "Level 2", level=2, position=2)
    _complete(db, user, done)

    stored = db.get(User, user.id)
    stored.level = 2
    db.commit()

    body = client.get(f"/api/topics/{topic.id}").json()
    assert [(lesson["title"], lesson["completed"]) for lesson in body["lessons"]] == [
        ("Done at Level 1", True),
        ("Level 2", False),
    ]
    assert body["lessons"][0]["best_correct"] == 1
    # Completed is counted over the same lessons as available, so it never exceeds it.
    assert (body["completed"], body["available"]) == (1, 2)
    progress = client.get("/api/progress").json()
    assert (progress["completed"], progress["available"]) == (1, 2)
    assert progress["suggestion"]["title"] == "Level 2"
    assert db.scalar(select(LessonCompletion).where(LessonCompletion.user_id == user.id))


def test_a_topic_with_nothing_at_your_level_has_no_circle(client, db, make_user):
    _sign_in(client, make_user, level=2)
    yours = _topic(db, "Singlish", position=0)
    other = _topic(db, "Hari Raya", position=1)
    _lesson(db, yours, "Level 2", level=2)
    _lesson(db, other, "Level 4", level=4)

    topics = client.get("/api/progress").json()["topics"]
    assert [topic["name"] for topic in topics] == ["Singlish"]


def test_no_suggestion_once_everything_at_your_level_is_done(client, db, make_user):
    user = _sign_in(client, make_user, level=2)
    topic = _topic(db)
    lesson = _lesson(db, topic, "Level 2", level=2)
    _lesson(db, topic, "Level 3", level=3)
    _complete(db, user, lesson)

    assert client.get("/api/progress").json()["suggestion"] is None


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
        command.upgrade(config, "head")
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
