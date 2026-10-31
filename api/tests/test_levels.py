"""SCRUM-110: levels and the aptitude quiz in the schema, and SCRUM-16's counting rule with
levels: each user sees the lessons at their level plus every lesson they have completed.

Users, lessons and aptitude questions share one scale of Level 1 to 5 (Epic 6).
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db import engine
from app.models import (
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
    assert {"level", "quiz_results", "quiz_taken_at", "intro_finished_at"} <= users
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


def test_quiz_results_are_saved_with_the_time_they_were_taken(db, make_user):
    user = db.merge(make_user())
    user.quiz_results = []
    with pytest.raises(IntegrityError):
        db.commit()


# --- AC4 and AC5: the latest quiz replaces the last, and keeps its own copy ---------------


def test_a_retake_replaces_the_previous_results_and_level(db, make_user):
    topic = _topic(db)
    question = _question(db, topic)
    user = db.merge(make_user())
    first = [{"question_id": str(question.id), "chosen_option_id": "b", "correct": False}]
    user.quiz_results, user.quiz_taken_at, user.level = first, datetime.now(UTC), 1
    db.commit()
    second = [{"question_id": str(question.id), "chosen_option_id": "a", "correct": True}]
    user.quiz_results, user.quiz_taken_at, user.level = second, datetime.now(UTC), 2
    db.commit()

    db.expire_all()
    stored = db.get(User, user.id)
    assert stored.quiz_results == second
    assert stored.level == 2


def test_editing_or_deactivating_a_question_leaves_saved_results_alone(db, make_user):
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
    user = db.merge(make_user())
    user.quiz_results, user.quiz_taken_at, user.level = [answer], datetime.now(UTC), 1
    db.commit()

    question.prompt = "Reworded"
    question.options = [{"id": "c", "text": "New"}, {"id": "d", "text": "Other"}]
    question.correct_option_id = "c"
    question.is_active = False
    db.commit()

    db.expire_all()
    assert db.get(User, user.id).quiz_results == [answer]


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
