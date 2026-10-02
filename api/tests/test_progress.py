"""SCRUM-16 AC7 and AC8: the progress figures behind the landing page circles.

What the circles look like is SCRUM-43 and lives in the front end. These tests cover the
counting rules, which are the part that has to be right.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models import Lesson, LessonCompletion, LessonStatus, Topic

USER = {"email": "user@example.com", "password": "Password123"}


def _topic(db, name: str, position: int = 0) -> Topic:
    topic = Topic(name=name, position=position)
    db.add(topic)
    db.commit()
    return topic


def _lesson(db, topic: Topic, title: str, status: LessonStatus = LessonStatus.PUBLISHED) -> Lesson:
    lesson = Lesson(
        title=title,
        content="...",
        topic=topic,
        status=status,
        published_at=datetime.now(UTC) if status == LessonStatus.PUBLISHED else None,
    )
    db.add(lesson)
    db.commit()
    return lesson


def _complete(db, user, lesson: Lesson, correct: bool = True) -> None:
    db.add(LessonCompletion(user_id=user.id, lesson_id=lesson.id, answered_correctly=correct))
    db.commit()


def _sign_in(client, make_user):
    user = make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    return user


def test_progress_needs_a_signed_in_user(client):
    response = client.get("/api/progress")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_signed_in"


def test_an_app_session_is_enough(client, make_user):
    _sign_in(client, make_user)
    assert client.get("/api/progress").status_code == 200


# --- Which topics appear (SCRUM-43 AC1) ----------------------------------------------------


def test_a_topic_with_no_published_lesson_has_no_circle(client, db, make_user):
    _sign_in(client, make_user)
    _topic(db, "Empty Topic")
    with_lesson = _topic(db, "Singlish")
    _lesson(db, with_lesson, "Lah, Leh and Lor")

    topics = client.get("/api/progress").json()["topics"]
    assert [topic["name"] for topic in topics] == ["Singlish"]


def test_a_topic_whose_only_lessons_are_drafts_has_no_circle(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db, "Workplace")
    _lesson(db, topic, "Draft lesson", status=LessonStatus.DRAFT)

    assert client.get("/api/progress").json()["topics"] == []


def test_circles_follow_the_order_administrators_set(client, db, make_user):
    _sign_in(client, make_user)
    for position, name in enumerate(["Workplace", "Festivals", "Singlish"]):
        _lesson(db, _topic(db, name, position), f"{name} lesson")

    topics = client.get("/api/progress").json()["topics"]
    assert [topic["name"] for topic in topics] == ["Workplace", "Festivals", "Singlish"]


def test_circles_in_the_same_position_fall_back_to_name(client, db, make_user):
    _sign_in(client, make_user)
    for name in ["Workplace", "Festivals", "Singlish"]:
        _lesson(db, _topic(db, name, position=3), f"{name} lesson")
    _lesson(db, _topic(db, "Hawker & Food", position=9), "Hawker lesson")

    topics = client.get("/api/progress").json()["topics"]
    assert [topic["name"] for topic in topics] == [
        "Festivals",
        "Singlish",
        "Workplace",
        "Hawker & Food",
    ]


# --- Archived topics are hidden (SCRUM-57) -------------------------------------------------


def _set_archived(db, topic: Topic, archived: bool) -> None:
    topic.archived_at = datetime.now(UTC) if archived else None
    db.commit()


def test_an_archived_topic_has_no_circle_and_the_totals_drop(client, db, make_user):
    user = _sign_in(client, make_user)
    singlish = _topic(db, "Singlish")
    workplace = _topic(db, "Workplace")
    _complete(db, user, _lesson(db, singlish, "One"))
    _lesson(db, singlish, "Two")
    _complete(db, user, _lesson(db, workplace, "Three"))
    _set_archived(db, singlish, True)

    body = client.get("/api/progress").json()
    assert [topic["name"] for topic in body["topics"]] == ["Workplace"]
    assert (body["completed"], body["available"]) == (1, 1)


def test_restoring_a_topic_brings_back_its_circle_and_progress(client, db, make_user):
    user = _sign_in(client, make_user)
    singlish = _topic(db, "Singlish")
    _complete(db, user, _lesson(db, singlish, "One"))
    _lesson(db, singlish, "Two")
    _set_archived(db, singlish, True)
    assert client.get("/api/progress").json()["available"] == 0

    _set_archived(db, singlish, False)

    body = client.get("/api/progress").json()
    assert [(t["name"], t["completed"], t["available"]) for t in body["topics"]] == [
        ("Singlish", 1, 2)
    ]
    assert (body["completed"], body["available"]) == (1, 2)


# --- The two figures (SCRUM-16 AC7) --------------------------------------------------------


def test_a_topic_with_no_completions_reads_zero_out_of_available(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "One")
    _lesson(db, topic, "Two")

    assert client.get("/api/progress").json()["topics"][0] == {
        "id": str(topic.id),
        "name": "Singlish",
        "completed": 0,
        "available": 2,
    }


def test_completed_counts_the_users_finished_lessons(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    first = _lesson(db, topic, "One")
    _lesson(db, topic, "Two")
    _lesson(db, topic, "Three")
    _complete(db, user, first)

    topic_progress = client.get("/api/progress").json()["topics"][0]
    assert (topic_progress["completed"], topic_progress["available"]) == (1, 3)


def test_a_wrong_answer_still_counts_as_completed(client, db, make_user):
    """SCRUM-16 AC3: completion does not depend on correctness."""
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _complete(db, user, _lesson(db, topic, "One"), correct=False)

    assert client.get("/api/progress").json()["topics"][0]["completed"] == 1


def test_overall_is_the_sum_across_topics(client, db, make_user):
    user = _sign_in(client, make_user)
    singlish = _topic(db, "Singlish")
    workplace = _topic(db, "Workplace")
    _complete(db, user, _lesson(db, singlish, "One"))
    _lesson(db, singlish, "Two")
    _complete(db, user, _lesson(db, workplace, "Three"))

    body = client.get("/api/progress").json()
    assert (body["completed"], body["available"]) == (2, 3)


def test_another_users_progress_is_not_counted(client, db, make_user):
    _sign_in(client, make_user)
    someone_else = make_user(email="other@example.com")
    topic = _topic(db, "Singlish")
    _complete(db, someone_else, _lesson(db, topic, "One"))

    assert client.get("/api/progress").json()["topics"][0]["completed"] == 0


# --- Only published lessons count (SCRUM-16 AC8) -------------------------------------------


def test_draft_and_withdrawn_lessons_are_not_available(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Published")
    _lesson(db, topic, "Draft", status=LessonStatus.DRAFT)
    _lesson(db, topic, "Withdrawn", status=LessonStatus.WITHDRAWN)

    assert client.get("/api/progress").json()["topics"][0]["available"] == 1


def test_withdrawing_a_completed_lesson_removes_it_from_both_figures(client, db, make_user):
    """SCRUM-16 AC8: a circle can never read "3 / 2" after SCRUM-52 withdraws a lesson."""
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    withdrawn = _lesson(db, topic, "One")
    _complete(db, user, withdrawn)
    _complete(db, user, _lesson(db, topic, "Two"))

    before = client.get("/api/progress").json()["topics"][0]
    assert (before["completed"], before["available"]) == (2, 2)

    withdrawn.status = LessonStatus.WITHDRAWN
    withdrawn.withdrawn_at = datetime.now(UTC)
    db.commit()

    after = client.get("/api/progress").json()["topics"][0]
    assert (after["completed"], after["available"]) == (1, 1)


def test_the_completion_row_survives_withdrawal(client, db, make_user):
    """The lesson leaves the circle but stays in the user's history (SCRUM-52 AC4)."""
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "One")
    _complete(db, user, lesson)

    lesson.status = LessonStatus.WITHDRAWN
    db.commit()

    kept = db.scalars(select(LessonCompletion).where(LessonCompletion.user_id == user.id)).all()
    assert [row.lesson_id for row in kept] == [lesson.id]


def test_a_lesson_with_no_topic_is_not_counted(client, db, make_user):
    """A draft can exist without a topic; publishing requires one (SCRUM-56)."""
    _sign_in(client, make_user)
    orphan = Lesson(title="No topic", content="...", status=LessonStatus.PUBLISHED)
    db.add(orphan)
    db.commit()

    body = client.get("/api/progress").json()
    assert body["topics"] == []
    assert body["available"] == 0
