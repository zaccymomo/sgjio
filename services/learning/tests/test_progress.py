"""SCRUM-16 AC7 and AC8: the progress figures behind the landing page circles.
(Ported from api/tests/test_progress.py.)

What the circles look like is SCRUM-43 and lives in the front end. These tests cover the
counting rules, which are the part that has to be right.
"""

from sqlalchemy import select, text

from app.db import engine
from app.models import LessonCompletion
from tests.conftest import sign_in
from tests.support.records import complete, quiz


def _sign_in(client, make_user):
    user = make_user("user@example.com")
    sign_in(client, user)
    return user


def test_progress_needs_a_signed_in_user(client):
    response = client.get("/api/progress")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_signed_in"


def test_a_request_that_did_not_come_through_the_gateway_is_refused(client, make_user):
    user = make_user()
    headers = user.headers() | {"X-Gateway-Key": "wrong"}
    assert client.get("/api/progress", headers=headers).status_code == 401


def test_an_app_session_is_enough(client, make_user):
    _sign_in(client, make_user)
    assert client.get("/api/progress").status_code == 200


# --- Which topics appear (SCRUM-43 AC1) ----------------------------------------------------


def test_a_topic_with_no_published_lesson_has_no_circle(client, content, make_user):
    _sign_in(client, make_user)
    content.topic("Empty Topic")
    content.lesson(content.topic("Singlish"), "Lah, Leh and Lor")

    topics = client.get("/api/progress").json()["topics"]
    assert [topic["name"] for topic in topics] == ["Singlish"]


def test_a_topic_whose_only_lessons_are_drafts_has_no_circle(client, content, make_user):
    _sign_in(client, make_user)
    content.lesson(content.topic("Workplace"), "Draft lesson", status="draft")

    assert client.get("/api/progress").json()["topics"] == []


def test_circles_follow_the_order_administrators_set(client, content, make_user):
    _sign_in(client, make_user)
    for position, name in enumerate(["Workplace", "Festivals", "Singlish"]):
        content.lesson(content.topic(name, position), f"{name} lesson")

    topics = client.get("/api/progress").json()["topics"]
    assert [topic["name"] for topic in topics] == ["Workplace", "Festivals", "Singlish"]


def test_circles_in_the_same_position_fall_back_to_name(client, content, make_user):
    _sign_in(client, make_user)
    for name in ["Workplace", "Festivals", "Singlish"]:
        content.lesson(content.topic(name, position=3), f"{name} lesson")
    content.lesson(content.topic("Hawker & Food", position=9), "Hawker lesson")

    topics = client.get("/api/progress").json()["topics"]
    assert [topic["name"] for topic in topics] == [
        "Festivals",
        "Singlish",
        "Workplace",
        "Hawker & Food",
    ]


def test_a_reorder_moves_the_circles(client, content, make_user):
    _sign_in(client, make_user)
    first, second = content.topic("First", 0), content.topic("Second", 1)
    content.lesson(first, "A")
    content.lesson(second, "B")
    content.update_topic(first, position=2)

    topics = client.get("/api/progress").json()["topics"]
    assert [topic["name"] for topic in topics] == ["Second", "First"]


# --- Archived topics are hidden (SCRUM-57) -------------------------------------------------


def test_an_archived_topic_has_no_circle_and_the_totals_drop(client, db, content, make_user):
    user = _sign_in(client, make_user)
    singlish = content.topic("Singlish")
    workplace = content.topic("Workplace")
    complete(db, user, content.lesson(singlish, "One"))
    content.lesson(singlish, "Two")
    complete(db, user, content.lesson(workplace, "Three"))
    content.archive(singlish)

    body = client.get("/api/progress").json()
    assert [topic["name"] for topic in body["topics"]] == ["Workplace"]
    assert (body["completed"], body["available"]) == (1, 1)


def test_restoring_a_topic_brings_back_its_circle_and_progress(client, db, content, make_user):
    user = _sign_in(client, make_user)
    singlish = content.topic("Singlish")
    complete(db, user, content.lesson(singlish, "One"))
    content.lesson(singlish, "Two")
    content.archive(singlish)
    assert client.get("/api/progress").json()["available"] == 0

    content.restore_topic(singlish)

    body = client.get("/api/progress").json()
    assert [(t["name"], t["completed"], t["available"]) for t in body["topics"]] == [
        ("Singlish", 1, 2)
    ]
    assert (body["completed"], body["available"]) == (1, 2)


# --- The two figures (SCRUM-16 AC7) --------------------------------------------------------


def test_a_topic_with_no_completions_reads_zero_out_of_available(client, content, make_user):
    _sign_in(client, make_user)
    topic = content.topic("Singlish")
    content.lesson(topic, "One")
    content.lesson(topic, "Two")

    assert client.get("/api/progress").json()["topics"][0] == {
        "id": str(topic.id),
        "name": "Singlish",
        "completed": 0,
        "exempted": 0,
        "available": 2,
        "level": 0,
    }


def test_completed_counts_the_users_finished_lessons(client, db, content, make_user):
    user = _sign_in(client, make_user)
    topic = content.topic("Singlish")
    first = content.lesson(topic, "One")
    content.lesson(topic, "Two")
    content.lesson(topic, "Three")
    complete(db, user, first)

    topic_progress = client.get("/api/progress").json()["topics"][0]
    assert (topic_progress["completed"], topic_progress["available"]) == (1, 3)


def test_circle_counts_completed_and_exempted_lessons_once(client, db, content, make_user):
    user = _sign_in(client, make_user)
    topic = content.topic("Singlish")
    first = content.lesson(topic, "One", level=1)
    content.lesson(topic, "Two", level=2)
    content.lesson(topic, "Three", level=3)
    complete(db, user, first)
    quiz(db, user, {topic: 2})

    body = client.get("/api/progress").json()
    assert body["topics"][0] | {"id": None, "name": None} == {
        "id": None,
        "name": None,
        "completed": 2,
        "exempted": 1,
        "available": 3,
        # SCRUM-100: Levels 1 and 2 are covered, Level 3 is not.
        "level": 2,
    }
    assert (body["completed"], body["exempted"], body["available"]) == (2, 1, 3)
    assert body["aptitude_taken"] is True


def test_a_wrong_answer_still_counts_as_completed(client, db, content, make_user):
    """SCRUM-16 AC3: completion does not depend on correctness."""
    user = _sign_in(client, make_user)
    complete(db, user, content.lesson(content.topic("Singlish"), "One"), correct=0)

    assert client.get("/api/progress").json()["topics"][0]["completed"] == 1


def test_overall_is_the_sum_across_topics(client, db, content, make_user):
    user = _sign_in(client, make_user)
    singlish = content.topic("Singlish")
    workplace = content.topic("Workplace")
    complete(db, user, content.lesson(singlish, "One"))
    content.lesson(singlish, "Two")
    complete(db, user, content.lesson(workplace, "Three"))

    body = client.get("/api/progress").json()
    assert (body["completed"], body["available"]) == (2, 3)


def test_another_users_progress_is_not_counted(client, db, content, make_user):
    _sign_in(client, make_user)
    someone_else = make_user("other@example.com")
    complete(db, someone_else, content.lesson(content.topic("Singlish"), "One"))

    assert client.get("/api/progress").json()["topics"][0]["completed"] == 0


# --- Only published lessons count (SCRUM-16 AC8) -------------------------------------------


def test_draft_and_withdrawn_lessons_are_not_available(client, content, make_user):
    _sign_in(client, make_user)
    topic = content.topic("Singlish")
    content.lesson(topic, "Published")
    content.lesson(topic, "Draft", status="draft")
    content.lesson(topic, "Withdrawn", status="withdrawn")

    assert client.get("/api/progress").json()["topics"][0]["available"] == 1


def test_withdrawing_a_completed_lesson_removes_it_from_both_figures(
    client, db, content, make_user
):
    """SCRUM-16 AC8: a circle can never read "3 / 2" after SCRUM-52 withdraws a lesson."""
    user = _sign_in(client, make_user)
    topic = content.topic("Singlish")
    withdrawn = content.lesson(topic, "One")
    complete(db, user, withdrawn)
    complete(db, user, content.lesson(topic, "Two"))

    before = client.get("/api/progress").json()["topics"][0]
    assert (before["completed"], before["available"]) == (2, 2)

    content.withdraw(withdrawn)

    after = client.get("/api/progress").json()["topics"][0]
    assert (after["completed"], after["available"]) == (1, 1)


def test_restoring_a_withdrawn_lesson_counts_it_again(client, db, content, make_user):
    user = _sign_in(client, make_user)
    lesson = content.lesson(content.topic("Singlish"), "One")
    complete(db, user, lesson)
    content.withdraw(lesson)
    content.restore(lesson)

    topic = client.get("/api/progress").json()["topics"][0]
    assert (topic["completed"], topic["available"]) == (1, 1)


def test_the_completion_row_survives_withdrawal(client, db, content, make_user):
    """The lesson leaves the circle but stays in the user's history (SCRUM-52 AC4)."""
    user = _sign_in(client, make_user)
    lesson = content.lesson(content.topic("Singlish"), "One")
    complete(db, user, lesson)

    content.withdraw(lesson)

    kept = db.scalars(select(LessonCompletion).where(LessonCompletion.user_id == user.id)).all()
    assert [row.lesson_id for row in kept] == [lesson.id]


def test_a_lesson_whose_topic_has_not_arrived_is_not_counted(client, bus, content, make_user):
    """Was "a lesson with no topic": a published lesson always has one now, but its topic's
    event can arrive after the lesson's. Until it does, the lesson is counted nowhere."""
    _sign_in(client, make_user)
    topic = content.topic("Singlish")
    content.lesson(topic, "One")
    (late_topic,) = [e for e in bus.sent if e["type"] == "content.topic.changed"]
    # As if the lesson's events had overtaken the topic's: Learning has not seen the topic.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM learnable_topics"))

    body = client.get("/api/progress").json()
    assert body["topics"] == []
    assert body["available"] == 0

    bus.deliver(late_topic)
    assert client.get("/api/progress").json()["available"] == 1
