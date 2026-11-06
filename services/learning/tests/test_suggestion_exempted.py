"""SCRUM-106 and SCRUM-107: the suggested lesson skips lessons the user is exempted from, and
says in one line why it was suggested. (Ported from api/tests/test_suggestion_exempted.py.)

The topic is the one with the smallest share covered, counting exempted lessons as the
circles do (SCRUM-104); within it, the lowest-level lesson neither completed nor exempted.
"""

import re

import pytest

from app.progress import suggestion_reason
from tests.conftest import sign_in
from tests.support.records import complete, quiz


@pytest.fixture
def lesson_in(content):
    def _lesson(topic, title, level=1, position=0):
        return content.lesson(
            topic, title, level=level, position=position, summary=f"About {title}"
        )

    return _lesson


def _sign_in(client, make_user):
    user = make_user("user@example.com")
    sign_in(client, user)
    return user


def _progress(client) -> dict:
    response = client.get("/api/progress")
    assert response.status_code == 200
    return response.json()


def _suggestion(client) -> dict | None:
    return _progress(client)["suggestion"]


# SCRUM-106


def test_the_topic_is_chosen_counting_exempted_lessons_as_covered(
    client, db, content, lesson_in, make_user
):
    """AC1: 2 of 4 exempted beats 1 of 4 completed, as the circles read."""
    user = _sign_in(client, make_user)
    exempted = content.topic("Mostly exempted", position=0)
    completed = content.topic("One completed", position=1)
    for level in range(1, 5):
        lesson_in(exempted, f"E{level}", level=level)
    completed_lessons = [lesson_in(completed, f"C{n}", position=n) for n in range(4)]
    complete(db, user, completed_lessons[0])
    quiz(db, user, {exempted: 2})

    suggestion = _suggestion(client)
    assert suggestion["topic_name"] == "One completed"
    assert suggestion["title"] == "C1"


def test_the_lowest_level_lesson_not_completed_or_exempted_is_picked(
    client, db, content, lesson_in, make_user
):
    """AC2: exempted Level 1 is skipped, completed Level 2 is skipped, Level 3 is next even
    though an administrator placed a Level 4 lesson before it."""
    user = _sign_in(client, make_user)
    topic = content.topic("Hawker culture")
    lesson_in(topic, "Level 4 placed first", level=4, position=0)
    lesson_in(topic, "Level 3", level=3, position=1)
    level_two = lesson_in(topic, "Level 2", level=2, position=2)
    lesson_in(topic, "Level 1", level=1, position=3)
    quiz(db, user, {topic: 1})
    complete(db, user, level_two)

    assert _suggestion(client)["title"] == "Level 3"


def test_within_a_level_the_order_administrators_set_decides(client, content, lesson_in, make_user):
    """AC2: two lessons at the same level go in lesson order."""
    _sign_in(client, make_user)
    topic = content.topic("Singlish")
    lesson_in(topic, "Second", level=2, position=1)
    lesson_in(topic, "First", level=2, position=0)

    assert _suggestion(client)["title"] == "First"


def test_a_topic_fully_exempted_moves_the_suggestion_on(client, db, content, lesson_in, make_user):
    """AC3: the first topic is all exempted, so the suggestion comes from the next one."""
    user = _sign_in(client, make_user)
    first = content.topic("All exempted", position=0)
    second = content.topic("Still to do", position=1)
    lesson_in(first, "Exempted one", level=1)
    lesson_in(first, "Exempted two", level=2)
    lesson_in(second, "Next up", level=3)
    quiz(db, user, {first: 5, second: 2})

    suggestion = _suggestion(client)
    assert suggestion["title"] == "Next up"
    assert suggestion["topic_name"] == "Still to do"


def test_nothing_is_suggested_once_everything_is_completed_or_exempted(
    client, db, content, lesson_in, make_user
):
    """AC4: a mix of completed and exempted covers everything, so there is no suggestion."""
    user = _sign_in(client, make_user)
    topic = content.topic("Singlish")
    lesson_in(topic, "Exempted", level=1)
    complete(db, user, lesson_in(topic, "Completed", level=3))
    quiz(db, user, {topic: 1})

    progress = _progress(client)
    assert progress["suggestion"] is None
    assert progress["completed"] == progress["available"] == 2


def test_completing_the_suggestion_brings_a_new_one_by_the_same_rules(
    client, db, content, lesson_in, make_user
):
    """AC5: the next one also skips exempted lessons."""
    user = _sign_in(client, make_user)
    topic = content.topic("Singlish")
    lesson_in(topic, "Exempted", level=1, position=0)
    level_two = lesson_in(topic, "Level 2", level=2, position=1)
    lesson_in(topic, "Level 3", level=3, position=2)
    quiz(db, user, {topic: 1})

    assert _suggestion(client)["title"] == "Level 2"
    complete(db, user, level_two)
    assert _suggestion(client)["title"] == "Level 3"


def test_skipping_the_quiz_exempts_nothing(client, content, lesson_in, make_user):
    """No quiz, no exemptions: the lowest-level lesson is suggested (SCRUM-98)."""
    _sign_in(client, make_user)
    topic = content.topic("Singlish")
    lesson_in(topic, "Level 2", level=2, position=0)
    lesson_in(topic, "Level 1", level=1, position=1)

    assert _suggestion(client)["title"] == "Level 1"


# SCRUM-107


def test_the_suggestion_names_the_weakest_topic(client, db, content, lesson_in, make_user):
    """AC1: the reason names the topic and says why it was chosen."""
    user = _sign_in(client, make_user)
    hawker = content.topic("Hawker culture", position=0)
    singlish = content.topic("Singlish", position=1)
    complete(db, user, lesson_in(singlish, "S1", position=0))
    lesson_in(singlish, "S2", position=1)
    lesson_in(hawker, "H1", position=0)
    lesson_in(hawker, "H2", position=1)
    complete(db, user, lesson_in(hawker, "H0", position=2))
    lesson_in(hawker, "H3", position=3)

    suggestion = _suggestion(client)
    assert suggestion["topic_name"] == "Hawker culture"
    assert (
        suggestion["reason"]
        == "The next lesson in Hawker culture, where you've done the least so far."
    )


def test_a_new_learner_is_told_it_is_a_place_to_start(client, content, lesson_in, make_user):
    """AC1: with nothing covered anywhere, 'least so far' would be odd, so it says start."""
    _sign_in(client, make_user)
    lesson_in(content.topic("Singlish", position=0), "S1")
    lesson_in(content.topic("Hawker culture", position=1), "H1")

    assert _suggestion(client)["reason"] == "The first lesson in Singlish, a good place to start."


def test_exempted_lessons_count_as_progress_in_the_reason(
    client, db, content, lesson_in, make_user
):
    """AC1: exemptions alone mean the learner is not starting from nothing."""
    user = _sign_in(client, make_user)
    singlish = content.topic("Singlish", position=0)
    hawker = content.topic("Hawker culture", position=1)
    lesson_in(singlish, "S1", level=1)
    lesson_in(singlish, "S2", level=2)
    lesson_in(hawker, "H1", level=1)
    quiz(db, user, {singlish: 1})

    assert (
        _suggestion(client)["reason"]
        == "The next lesson in Hawker culture, where you've done the least so far."
    )


def test_the_last_unfinished_topic_is_called_that(client, db, content, lesson_in, make_user):
    """AC1: with one topic left, 'the least so far' is replaced by what is true."""
    user = _sign_in(client, make_user)
    done = content.topic("Singlish", position=0)
    left = content.topic("Hawker culture", position=1)
    complete(db, user, lesson_in(done, "S1"))
    complete(db, user, lesson_in(left, "H1", position=0))
    lesson_in(left, "H2", position=1)

    assert (
        _suggestion(client)["reason"]
        == "The next lesson in Hawker culture, the only topic you haven't finished yet."
    )


def test_no_reason_mentions_a_level():
    """AC2: levels are not shown to users, so no wording of the reason names one."""
    for weakest in (True, False):
        for only_unfinished in (True, False):
            for nothing_covered in (True, False):
                reason = suggestion_reason(
                    "Singlish",
                    weakest=weakest,
                    only_unfinished=only_unfinished,
                    nothing_covered=nothing_covered,
                )
                assert "Singlish" in reason
                assert not re.search(r"level|\d", reason, re.IGNORECASE)
