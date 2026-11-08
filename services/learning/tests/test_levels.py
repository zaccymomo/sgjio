"""SCRUM-110: levels and the aptitude quiz in Learning's schema. (Ported from the Learning
half of api/tests/test_levels.py.)

Moved to Content: the lesson and question level constraints, a new lesson starting at
Level 1, a question needing a topic and listing its correct option. Dropped: the migration
tests (0012 -> 0013 -> 0014), which test the monolith's own history.
"""

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.aptitude import has_taken_quiz, quiz_attempt
from app.db import engine
from app.models import AptitudeAttempt
from tests.conftest import sign_in
from tests.support.records import complete


def _attempt(db, user, results):
    attempt = AptitudeAttempt(user_id=user.id, results=results)
    db.add(attempt)
    db.commit()
    return attempt


def test_the_quiz_tables_and_read_models_exist():
    schema = inspect(engine)
    quiz_attempts = {c["name"] for c in schema.get_columns("aptitude_attempts")}
    assert {"user_id", "taken_at", "results"} <= quiz_attempts
    # A user is Identity's: no foreign key.
    assert schema.get_foreign_keys("aptitude_attempts") == []
    questions = {c["name"] for c in schema.get_columns("quiz_questions")}
    assert {
        "topic_id",
        "level",
        "prompt",
        "options",
        "correct_option_id",
        "is_active",
        "version",
    } <= questions
    assert "level" in {c["name"] for c in schema.get_columns("learnable_lessons")}


@pytest.mark.parametrize("level", ["NULL", "0", "6"])
def test_a_learnable_lesson_without_a_valid_level_is_refused(level):
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO learnable_lessons (id, topic_id, level, position, created_at,"
                " display_title, publication_state, learner_visible, first_published_at,"
                " latest_version_id, latest_version_number, version) VALUES"
                f" (gen_random_uuid(), gen_random_uuid(), {level}, 0, now(), 'X', 'published',"
                " true, now(), gen_random_uuid(), 1, 1)"
            )
        )


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
    other = make_user("other@example.com")
    _attempt(db, other, results=[])
    assert quiz_attempt(db, user.id) is None
    assert has_taken_quiz(db, other.id)


# --- AC5: each quiz keeps its own copy of the questions ------------------------------------


def test_editing_or_deactivating_a_question_leaves_past_results_alone(db, content, make_user):
    topic = content.topic()
    question = content.question(topic)
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

    content.update_question(
        question,
        prompt="Reworded",
        options=[{"id": "c", "text": "New"}, {"id": "d", "text": "Other"}],
        correct_option_id="c",
        is_active=False,
    )

    db.expire_all()
    assert db.get(AptitudeAttempt, attempt.id).results == [answer]


def test_deleting_an_account_deletes_its_quizzes(db, identity, make_user):
    user = make_user()
    _attempt(db, user, results=[])
    identity.delete(user)
    assert db.scalar(select(AptitudeAttempt)) is None


# --- SCRUM-104 AC4: lessons are no longer hidden by level --------------------------------


def test_a_user_sees_lessons_at_every_level(client, db, content, make_user):
    user = make_user()
    sign_in(client, user)
    topic = content.topic()
    done = content.lesson(topic, "Level 1", level=1, position=0)
    content.lesson(topic, "Level 3", level=3, position=1)
    content.lesson(topic, "Level 5", level=5, position=2)
    complete(db, user, done)

    body = client.get(f"/api/topics/{topic.id}").json()
    assert [lesson["title"] for lesson in body["lessons"]] == ["Level 1", "Level 3", "Level 5"]
    assert (body["completed"], body["available"]) == (1, 3)

    progress = client.get("/api/progress").json()
    assert (progress["completed"], progress["available"]) == (1, 3)
    assert progress["suggestion"]["title"] == "Level 3"
