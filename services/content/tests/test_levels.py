"""SCRUM-110: lesson and aptitude question levels in the schema (ported from the monolith's
test_levels.py).

Lessons and aptitude questions share one scale of Level 1 to 5 (Epic 6), which the database
itself checks. The quiz attempts, user levels and the 0012-0014 migration tests in the
monolith's file belong to Learning (quizzes) or to the monolith's migration history, which
this service's fresh baseline does not have.
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import engine
from app.models import AptitudeQuestion, Lesson, Topic

OPTIONS = [{"id": "a", "text": "Chope"}, {"id": "b", "text": "Queue"}]


def _topic(db, name: str = "Hawker culture", position: int = 0) -> Topic:
    topic = Topic(name=name, position=position)
    db.add(topic)
    db.commit()
    return topic


def _question(db, topic: Topic, level: int | None = 1, **overrides) -> AptitudeQuestion:
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
    with pytest.raises(IntegrityError, match="level"), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO lessons (id, title, status, position, level) "
                f"VALUES (gen_random_uuid(), 'X', 'draft', 0, {level})"
            )
        )


def test_a_lesson_with_a_valid_level_is_accepted():
    # The control for the test above: the raw INSERT is otherwise valid, so the refusals
    # come from the level check. (`position` has no database default, so an INSERT
    # without it, as the monolith's test had, fails whatever the level.)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO lessons (id, title, status, position, level) "
                "VALUES (gen_random_uuid(), 'X', 'draft', 0, 5)"
            )
        )


@pytest.mark.parametrize("level", [None, 0, 6])
def test_a_question_without_a_valid_level_is_refused(db, level):
    topic = _topic(db)
    with pytest.raises(IntegrityError, match="level"):
        _question(db, topic, level=level)


def test_a_question_without_a_topic_is_refused(db):
    with pytest.raises(IntegrityError, match="topic_id"):
        db.add(AptitudeQuestion(level=1, prompt="?", options=OPTIONS, correct_option_id="a"))
        db.commit()
