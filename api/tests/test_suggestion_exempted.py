"""SCRUM-106 and SCRUM-107: the suggested lesson skips lessons the user is exempted from, and
says in one line why it was suggested.

The topic is the one with the smallest share covered, counting exempted lessons as the
circles do (SCRUM-104); within it, the lowest-level lesson neither completed nor exempted.
"""

import re
from datetime import UTC, datetime

from app.models import (
    AptitudeAttempt,
    Lesson,
    LessonCompletion,
    LessonStatus,
    LessonVersion,
    Topic,
    TopicExemption,
)
from app.progress import suggestion_reason

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


def _topic(db, name: str, position: int = 0) -> Topic:
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
    )
    db.add(lesson)
    db.flush()
    db.add(
        LessonVersion(
            lesson_id=lesson.id,
            number=1,
            title=title,
            summary=f"About {title}",
            doc=DOC,
            published_at=now,
        )
    )
    db.commit()
    return lesson


def _quiz(db, user, exemptions: dict[Topic, int]) -> None:
    """A completed quiz and its exemptions, saved together (SCRUM-113)."""
    db.add(AptitudeAttempt(user_id=user.id, results=[{"correct": True}]))
    db.flush()
    for topic, level in exemptions.items():
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=level))
    db.commit()


def _complete(db, user, lesson: Lesson) -> None:
    db.add(LessonCompletion(user_id=user.id, lesson_id=lesson.id, best_correct=1, best_scored=1))
    db.commit()


def _sign_in(client, make_user):
    user = make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    return user


def _progress(client) -> dict:
    response = client.get("/api/progress")
    assert response.status_code == 200
    return response.json()


def _suggestion(client) -> dict | None:
    return _progress(client)["suggestion"]


# SCRUM-106


def test_the_topic_is_chosen_counting_exempted_lessons_as_covered(client, db, make_user):
    """AC1: 2 of 4 exempted beats 1 of 4 completed, as the circles read."""
    user = _sign_in(client, make_user)
    exempted = _topic(db, "Mostly exempted", position=0)
    completed = _topic(db, "One completed", position=1)
    for level in range(1, 5):
        _lesson(db, exempted, f"E{level}", level=level)
    completed_lessons = [_lesson(db, completed, f"C{n}", position=n) for n in range(4)]
    _complete(db, user, completed_lessons[0])
    _quiz(db, user, {exempted: 2})

    suggestion = _suggestion(client)
    assert suggestion["topic_name"] == "One completed"
    assert suggestion["title"] == "C1"


def test_the_lowest_level_lesson_not_completed_or_exempted_is_picked(client, db, make_user):
    """AC2: exempted Level 1 is skipped, completed Level 2 is skipped, Level 3 is next even
    though an administrator placed a Level 4 lesson before it."""
    user = _sign_in(client, make_user)
    topic = _topic(db, "Hawker culture")
    _lesson(db, topic, "Level 4 placed first", level=4, position=0)
    _lesson(db, topic, "Level 3", level=3, position=1)
    level_two = _lesson(db, topic, "Level 2", level=2, position=2)
    _lesson(db, topic, "Level 1", level=1, position=3)
    _quiz(db, user, {topic: 1})
    _complete(db, user, level_two)

    assert _suggestion(client)["title"] == "Level 3"


def test_within_a_level_the_order_administrators_set_decides(client, db, make_user):
    """AC2: two lessons at the same level go in lesson order."""
    _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Second", level=2, position=1)
    _lesson(db, topic, "First", level=2, position=0)

    assert _suggestion(client)["title"] == "First"


def test_a_topic_fully_exempted_moves_the_suggestion_on(client, db, make_user):
    """AC3: the first topic is all exempted, so the suggestion comes from the next one."""
    user = _sign_in(client, make_user)
    first = _topic(db, "All exempted", position=0)
    second = _topic(db, "Still to do", position=1)
    _lesson(db, first, "Exempted one", level=1)
    _lesson(db, first, "Exempted two", level=2)
    _lesson(db, second, "Next up", level=3)
    _quiz(db, user, {first: 5, second: 2})

    suggestion = _suggestion(client)
    assert suggestion["title"] == "Next up"
    assert suggestion["topic_name"] == "Still to do"


def test_nothing_is_suggested_once_everything_is_completed_or_exempted(client, db, make_user):
    """AC4: a mix of completed and exempted covers everything, so there is no suggestion."""
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Exempted", level=1)
    _complete(db, user, _lesson(db, topic, "Completed", level=3))
    _quiz(db, user, {topic: 1})

    progress = _progress(client)
    assert progress["suggestion"] is None
    assert progress["completed"] == progress["available"] == 2


def test_completing_the_suggestion_brings_a_new_one_by_the_same_rules(client, db, make_user):
    """AC5: the next one also skips exempted lessons."""
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Exempted", level=1, position=0)
    level_two = _lesson(db, topic, "Level 2", level=2, position=1)
    _lesson(db, topic, "Level 3", level=3, position=2)
    _quiz(db, user, {topic: 1})

    assert _suggestion(client)["title"] == "Level 2"
    _complete(db, user, level_two)
    assert _suggestion(client)["title"] == "Level 3"


def test_skipping_the_quiz_exempts_nothing(client, db, make_user):
    """No quiz, no exemptions: the lowest-level lesson is suggested (SCRUM-98)."""
    _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Level 2", level=2, position=0)
    _lesson(db, topic, "Level 1", level=1, position=1)

    assert _suggestion(client)["title"] == "Level 1"


# SCRUM-107


def test_the_suggestion_names_the_weakest_topic(client, db, make_user):
    """AC1: the reason names the topic and says why it was chosen."""
    user = _sign_in(client, make_user)
    hawker = _topic(db, "Hawker culture", position=0)
    singlish = _topic(db, "Singlish", position=1)
    _complete(db, user, _lesson(db, singlish, "S1", position=0))
    _lesson(db, singlish, "S2", position=1)
    _lesson(db, hawker, "H1", position=0)
    _lesson(db, hawker, "H2", position=1)
    _complete(db, user, _lesson(db, hawker, "H0", position=2))
    _lesson(db, hawker, "H3", position=3)

    suggestion = _suggestion(client)
    assert suggestion["topic_name"] == "Hawker culture"
    assert (
        suggestion["reason"]
        == "The next lesson in Hawker culture, where you've done the least so far."
    )


def test_a_new_learner_is_told_it_is_a_place_to_start(client, db, make_user):
    """AC1: with nothing covered anywhere, 'least so far' would be odd, so it says start."""
    _sign_in(client, make_user)
    _lesson(db, _topic(db, "Singlish", position=0), "S1")
    _lesson(db, _topic(db, "Hawker culture", position=1), "H1")

    assert _suggestion(client)["reason"] == "The first lesson in Singlish, a good place to start."


def test_exempted_lessons_count_as_progress_in_the_reason(client, db, make_user):
    """AC1: exemptions alone mean the learner is not starting from nothing."""
    user = _sign_in(client, make_user)
    singlish = _topic(db, "Singlish", position=0)
    hawker = _topic(db, "Hawker culture", position=1)
    _lesson(db, singlish, "S1", level=1)
    _lesson(db, singlish, "S2", level=2)
    _lesson(db, hawker, "H1", level=1)
    _quiz(db, user, {singlish: 1})

    assert (
        _suggestion(client)["reason"]
        == "The next lesson in Hawker culture, where you've done the least so far."
    )


def test_the_last_unfinished_topic_is_called_that(client, db, make_user):
    """AC1: with one topic left, 'the least so far' is replaced by what is true."""
    user = _sign_in(client, make_user)
    done = _topic(db, "Singlish", position=0)
    left = _topic(db, "Hawker culture", position=1)
    _complete(db, user, _lesson(db, done, "S1"))
    _complete(db, user, _lesson(db, left, "H1", position=0))
    _lesson(db, left, "H2", position=1)

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
