"""SCRUM-6: a suggested next lesson beside the progress circles, drawn from the topic where
progress is weakest, and none once everything available is completed.
(Ported from api/tests/test_suggestion.py.)"""

import pytest

from tests.conftest import sign_in
from tests.support.records import complete


@pytest.fixture
def lesson_in(content):
    def _lesson(topic, title, position=0, status="published", versioned=True):
        lesson = content.lesson(
            topic,
            title,
            position=position,
            status=status if versioned else "draft",
            summary=f"About {title}",
        )
        if not versioned and status == "published":
            # Published, but its deck has not reached Learning.
            content.publish(lesson, summary=f"About {title}", deliver_deck=False)
        return lesson

    return _lesson


def _suggestion(client) -> dict | None:
    response = client.get("/api/progress")
    assert response.status_code == 200
    return response.json()["suggestion"]


def _sign_in(client, make_user):
    user = make_user("user@example.com")
    sign_in(client, user)
    return user


def test_the_landing_page_figures_include_a_suggestion(client, content, lesson_in, make_user):
    """AC1: shown alongside the circles, with what the card needs."""
    _sign_in(client, make_user)
    topic = content.topic("Singlish")
    lesson = lesson_in(topic, "Lah, Leh and Lor")

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


def test_it_comes_from_the_topic_with_the_smallest_share_completed(
    client, db, content, lesson_in, make_user
):
    """AC2: 1 of 2 done beats 1 of 4 done, whatever the order of the topics."""
    user = _sign_in(client, make_user)
    half = content.topic("Half done", position=0)
    quarter = content.topic("Quarter done", position=1)
    half_lessons = [lesson_in(half, f"H{n}", position=n) for n in range(2)]
    quarter_lessons = [lesson_in(quarter, f"Q{n}", position=n) for n in range(4)]
    complete(db, user, half_lessons[0])
    complete(db, user, quarter_lessons[0])

    assert _suggestion(client)["title"] == "Q1"


def test_ties_go_to_the_earlier_topic_and_its_first_lesson(client, content, lesson_in, make_user):
    """The open decision: with no activity at all, the first lesson of the first topic in the
    order administrators set (docs/decisions.md)."""
    _sign_in(client, make_user)
    second = content.topic("A comes second", position=1)
    first = content.topic("B comes first", position=0)
    lesson_in(second, "Second topic lesson")
    lesson_in(first, "Later lesson", position=1)
    lesson_in(first, "Earlier lesson", position=0)

    assert _suggestion(client)["title"] == "Earlier lesson"


def test_completing_the_suggestion_moves_it_on(client, db, content, lesson_in, make_user):
    """AC4: a new suggestion once the last one is completed."""
    user = _sign_in(client, make_user)
    topic = content.topic("Singlish")
    first = lesson_in(topic, "First", position=0)
    lesson_in(topic, "Second", position=1)

    assert _suggestion(client)["title"] == "First"
    complete(db, user, first, correct=0)
    assert _suggestion(client)["title"] == "Second"


def test_a_lesson_completed_out_of_order_is_skipped(client, db, content, lesson_in, make_user):
    """AC5: a lesson picked from a topic directly counts the same, so it is never suggested."""
    user = _sign_in(client, make_user)
    topic = content.topic("Singlish")
    lesson_in(topic, "First", position=0)
    second = lesson_in(topic, "Second", position=1)
    complete(db, user, second, correct=0)

    assert _suggestion(client)["title"] == "First"


def test_nothing_is_suggested_once_everything_is_completed(
    client, db, content, lesson_in, make_user
):
    """AC6."""
    user = _sign_in(client, make_user)
    complete(db, user, lesson_in(content.topic("Singlish"), "Only lesson"), correct=0)

    assert _suggestion(client) is None


def test_nothing_is_suggested_when_no_lessons_are_published(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    lesson_in(content.topic("Singlish"), "Draft", status="draft", versioned=False)

    assert _suggestion(client) is None


def test_only_lessons_learners_can_open_are_suggested(client, content, lesson_in, make_user):
    """Drafts, withdrawn lessons and archived topics are never suggested."""
    _sign_in(client, make_user)
    archived = content.topic("Archived", position=0, archived=True)
    lesson_in(archived, "In an archived topic")
    topic = content.topic("Singlish", position=1)
    lesson_in(topic, "Draft", position=0, status="draft", versioned=False)
    lesson_in(topic, "Withdrawn", position=1, status="withdrawn")
    lesson_in(topic, "Published", position=2)

    assert _suggestion(client)["title"] == "Published"


def test_a_published_lesson_whose_deck_has_not_arrived_is_passed_over(
    client, content, lesson_in, make_user
):
    """Was "a published lesson with no version": now a lesson whose deck is still on its
    way. It is invisible until the deck arrives, so the next one is suggested."""
    _sign_in(client, make_user)
    topic = content.topic("Singlish")
    lesson_in(topic, "Broken", position=0, versioned=False)
    lesson_in(topic, "Fine", position=1)

    assert _suggestion(client)["title"] == "Fine"


def test_the_suggestion_is_the_users_own(client, db, content, lesson_in, make_user):
    """Someone else's completions never move it."""
    _sign_in(client, make_user)
    other = make_user("other@example.com")
    topic = content.topic("Singlish")
    first = lesson_in(topic, "First", position=0)
    lesson_in(topic, "Second", position=1)
    complete(db, other, first, correct=0)

    assert _suggestion(client)["title"] == "First"
