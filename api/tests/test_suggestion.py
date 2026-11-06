"""SCRUM-6: a suggested next lesson beside the progress circles, drawn from the topic where
progress is weakest, and none once everything available is completed."""

from datetime import UTC, datetime

from app.models import Lesson, LessonCompletion, LessonStatus, LessonVersion, Topic

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


def _topic(db, name: str, position: int = 0, archived: bool = False) -> Topic:
    topic = Topic(name=name, position=position, archived_at=datetime.now(UTC) if archived else None)
    db.add(topic)
    db.commit()
    return topic


def _lesson(
    db,
    topic: Topic,
    title: str,
    position: int = 0,
    status: LessonStatus = LessonStatus.PUBLISHED,
    versioned: bool = True,
) -> Lesson:
    lesson = Lesson(title=title, topic=topic, status=status, position=position, draft=DOC)
    db.add(lesson)
    db.commit()
    if versioned:
        db.add(
            LessonVersion(
                lesson_id=lesson.id,
                number=1,
                title=title,
                summary=f"About {title}",
                doc=DOC,
                published_at=datetime.now(UTC),
            )
        )
        db.commit()
    return lesson


def _complete(db, user, lesson: Lesson) -> None:
    db.add(LessonCompletion(user_id=user.id, lesson_id=lesson.id, best_correct=0, best_scored=1))
    db.commit()


def _suggestion(client) -> dict | None:
    response = client.get("/api/progress")
    assert response.status_code == 200
    return response.json()["suggestion"]


def _sign_in(client, make_user):
    user = make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    return user


def test_the_landing_page_figures_include_a_suggestion(client, db, make_user):
    """AC1: shown alongside the circles, with what the card needs."""
    _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Lah, Leh and Lor")

    suggestion = _suggestion(client)
    assert suggestion == {
        "lesson_id": str(lesson.id),
        "title": "Lah, Leh and Lor",
        "summary": "About Lah, Leh and Lor",
        "reading_seconds": suggestion["reading_seconds"],
        "topic_id": str(topic.id),
        "topic_name": "Singlish",
        "reason": "The first lesson in Singlish, a good place to start.",
    }
    assert 0 < suggestion["reading_seconds"] <= 120


def test_it_comes_from_the_topic_with_the_smallest_share_completed(client, db, make_user):
    """AC2: 1 of 2 done beats 1 of 4 done, whatever the order of the topics."""
    user = _sign_in(client, make_user)
    half = _topic(db, "Half done", position=0)
    quarter = _topic(db, "Quarter done", position=1)
    half_lessons = [_lesson(db, half, f"H{n}", position=n) for n in range(2)]
    quarter_lessons = [_lesson(db, quarter, f"Q{n}", position=n) for n in range(4)]
    _complete(db, user, half_lessons[0])
    _complete(db, user, quarter_lessons[0])

    assert _suggestion(client)["title"] == "Q1"


def test_ties_go_to_the_earlier_topic_and_its_first_lesson(client, db, make_user):
    """The open decision: with no activity at all, the first lesson of the first topic in the
    order administrators set (docs/decisions.md)."""
    _sign_in(client, make_user)
    second = _topic(db, "A comes second", position=1)
    first = _topic(db, "B comes first", position=0)
    _lesson(db, second, "Second topic lesson")
    _lesson(db, first, "Later lesson", position=1)
    _lesson(db, first, "Earlier lesson", position=0)

    assert _suggestion(client)["title"] == "Earlier lesson"


def test_completing_the_suggestion_moves_it_on(client, db, make_user):
    """AC4: a new suggestion once the last one is completed."""
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    first = _lesson(db, topic, "First", position=0)
    _lesson(db, topic, "Second", position=1)

    assert _suggestion(client)["title"] == "First"
    _complete(db, user, first)
    assert _suggestion(client)["title"] == "Second"


def test_a_lesson_completed_out_of_order_is_skipped(client, db, make_user):
    """AC5: a lesson picked from a topic directly counts the same, so it is never suggested."""
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "First", position=0)
    second = _lesson(db, topic, "Second", position=1)
    _complete(db, user, second)

    assert _suggestion(client)["title"] == "First"


def test_nothing_is_suggested_once_everything_is_completed(client, db, make_user):
    """AC6."""
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _complete(db, user, _lesson(db, topic, "Only lesson"))

    assert _suggestion(client) is None


def test_nothing_is_suggested_when_no_lessons_are_published(client, db, make_user):
    _sign_in(client, make_user)
    _lesson(db, _topic(db, "Singlish"), "Draft", status=LessonStatus.DRAFT, versioned=False)

    assert _suggestion(client) is None


def test_only_lessons_learners_can_open_are_suggested(client, db, make_user):
    """Drafts, withdrawn lessons and archived topics are never suggested."""
    _sign_in(client, make_user)
    archived = _topic(db, "Archived", position=0, archived=True)
    _lesson(db, archived, "In an archived topic")
    topic = _topic(db, "Singlish", position=1)
    _lesson(db, topic, "Draft", position=0, status=LessonStatus.DRAFT, versioned=False)
    _lesson(db, topic, "Withdrawn", position=1, status=LessonStatus.WITHDRAWN)
    _lesson(db, topic, "Published", position=2)

    assert _suggestion(client)["title"] == "Published"


def test_a_published_lesson_with_no_version_is_passed_over(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Broken", position=0, versioned=False)
    _lesson(db, topic, "Fine", position=1)

    assert _suggestion(client)["title"] == "Fine"


def test_the_suggestion_is_the_users_own(client, db, make_user):
    """Someone else's completions never move it."""
    _sign_in(client, make_user)
    other = make_user(email="other@example.com")
    topic = _topic(db, "Singlish")
    first = _lesson(db, topic, "First", position=0)
    _lesson(db, topic, "Second", position=1)
    _complete(db, other, first)

    assert _suggestion(client)["title"] == "First"
