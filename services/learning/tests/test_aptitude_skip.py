"""SCRUM-98: skipping the aptitude quiz for now and taking it later. (Ported from
api/tests/test_aptitude_skip.py.)

Nothing is stored for a skip, so these tests are about a user with no quiz attempt: what
they see, and what happens when they take the quiz later on. AC1 itself, leaving for the
homepage, is the "Skip for now" button in `web/` and asks nothing of the server.
"""

import pytest
from sqlalchemy import select

from app.models import AptitudeAttempt, LessonCompletion, QuizQuestion, TopicExemption
from tests.conftest import sign_in
from tests.support.records import complete
from tests.test_aptitude import TOPICS


@pytest.fixture
def topics(content):
    return [content.topic(name, position) for position, name in enumerate(TOPICS)]


@pytest.fixture
def bank(content, topics):
    return content.full_bank(topics)


def _sign_in(client, make_user, **kwargs):
    user = make_user("user@example.com", **kwargs)
    sign_in(client, user)
    return user


def _progress(client) -> dict:
    response = client.get("/api/progress")
    assert response.status_code == 200
    return response.json()


def _wrong(question: QuizQuestion) -> str:
    return next(
        option["id"] for option in question.options if option["id"] != question.correct_option_id
    )


def _take_quiz(client, db) -> dict:
    """Answer every question in the first topic correctly and get every other topic wrong."""
    question = client.post("/api/aptitude/start").json()["question"]
    first_topic = question["topic_id"]
    answers = []
    while question is not None:
        model = db.get(QuizQuestion, question["id"])
        option = model.correct_option_id if question["topic_id"] == first_topic else _wrong(model)
        answers.append({"question_id": question["id"], "option_id": option})
        question = client.post("/api/aptitude/next", json={"answers": answers}).json()["question"]
    submitted = client.post("/api/aptitude/submit", json={"answers": answers})
    assert submitted.status_code == 200
    return {"topic_id": first_topic, "result": submitted.json()}


def test_circles_show_only_completed_lessons_without_a_quiz(client, db, content, make_user):
    """AC2: nothing is exempted, at any level."""
    user = _sign_in(client, make_user)
    topic = content.topic("Singlish", 0)
    complete(db, user, content.lesson(topic, "Done", level=1, position=0))
    content.lesson(topic, "Not done", level=1, position=1)
    content.lesson(topic, "Harder", level=2, position=2)

    progress = _progress(client)
    assert (progress["completed"], progress["exempted"], progress["available"]) == (1, 0, 3)
    circle = progress["topics"][0]
    assert (circle["completed"], circle["exempted"], circle["available"]) == (1, 0, 3)

    page = client.get(f"/api/topics/{topic.id}").json()
    assert not any(lesson["exempted"] for lesson in page["lessons"])


def test_the_prompt_stays_until_the_quiz_is_completed(client, db, bank, make_user):
    """AC3: the homepage shows its prompt while `aptitude_taken` is false."""
    _sign_in(client, make_user)
    assert _progress(client)["aptitude_taken"] is False

    # Starting is not completing: an unfinished quiz leaves the prompt in place.
    assert client.post("/api/aptitude/start").status_code == 200
    assert _progress(client)["aptitude_taken"] is False

    _take_quiz(client, db)
    assert _progress(client)["aptitude_taken"] is True


def test_someone_who_also_skipped_profile_setup_can_take_the_quiz(client, db, bank, make_user):
    """AC4: profile setup can be skipped too (SCRUM-14), and the prompt still has to work."""
    user = _sign_in(client, make_user, profile_completed=False)

    taken = _take_quiz(client, db)

    assert taken["result"]["placements"]
    assert db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == user.id)) is not None


def test_taking_the_quiz_later_keeps_completed_lessons_and_scores(
    client, db, content, topics, bank, make_user
):
    """AC5: a lesson completed before the quiz stays completed, with its score, and is not
    also counted as exempted."""
    user = _sign_in(client, make_user)
    question = client.post("/api/aptitude/start").json()["question"]
    topic = next(t for t in topics if str(t.id) == question["topic_id"])
    lesson = content.lesson(topic, "Done before the quiz", level=1, position=99)
    db.add(LessonCompletion(user_id=user.id, lesson_id=lesson.id, best_correct=1, best_scored=2))
    db.commit()

    taken = _take_quiz(client, db)

    # The whole topic is exempted, so the lesson would be labelled so if not for its completion.
    exemption = db.scalar(
        select(TopicExemption).where(
            TopicExemption.user_id == user.id, TopicExemption.topic_id == topic.id
        )
    )
    assert exemption.level == 5
    assert taken["topic_id"] == str(topic.id)

    db.expire_all()
    completion = db.scalar(
        select(LessonCompletion).where(
            LessonCompletion.user_id == user.id, LessonCompletion.lesson_id == lesson.id
        )
    )
    assert (completion.best_correct, completion.best_scored) == (1, 2)

    page = client.get(f"/api/topics/{topic.id}").json()
    row = next(item for item in page["lessons"] if item["id"] == str(lesson.id))
    assert row["completed"] is True
    assert row["exempted"] is False
    assert (row["best_correct"], row["best_scored"]) == (1, 2)
    # Counted once: every lesson is covered, and all but this one by the quiz.
    assert page["completed"] == page["available"]
    assert page["exempted"] == page["available"] - 1
