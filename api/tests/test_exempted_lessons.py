"""SCRUM-104: each topic lists all its lessons, with the ones the user is exempted from marked.

The aptitude quiz gives each topic an exemption level (SCRUM-113, `app/exemptions.py`).
Every published lesson in that topic at or below it is exempted: labelled "Exempted" on the
topic page until completed, and counted as completed in the circles, the overall figure and
the topic page, while still opening like any other lesson.
"""

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

USER = {"email": "user@example.com", "password": "Password123"}
OTHER = {"email": "other@example.com", "password": "Password123"}

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


def _lesson(
    db,
    topic: Topic,
    title: str,
    level: int,
    position: int = 0,
    status: LessonStatus = LessonStatus.PUBLISHED,
) -> Lesson:
    lesson = Lesson(title=title, topic=topic, level=level, position=position, status=status)
    db.add(lesson)
    db.flush()
    if status != LessonStatus.DRAFT:
        now = datetime.now(UTC)
        lesson.published_at = now
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


def _sign_in(client, make_user, account=USER):
    user = make_user(**account)
    client.post("/api/auth/sign-in", json=account)
    return user


def _circles(client) -> dict[str, tuple[int, int]]:
    body = client.get("/api/progress").json()
    return {t["name"]: (t["completed"], t["available"]) for t in body["topics"]}


def _rows(client, topic: Topic) -> dict[str, dict]:
    lessons = client.get(f"/api/topics/{topic.id}").json()["lessons"]
    return {lesson["title"]: lesson for lesson in lessons}


# --- AC1: lessons at or below the topic's exemption level are exempted -------------------


def test_lessons_at_or_below_the_exemption_level_are_exempted(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    for level in (1, 2, 3):
        _lesson(db, topic, f"Level {level}", level=level)
    _quiz(db, user, {topic: 2})

    rows = _rows(client, topic)
    assert [rows[f"Level {n}"]["exempted"] for n in (1, 2, 3)] == [True, True, False]
    assert _circles(client) == {"Singlish": (2, 3)}


def test_exemption_level_0_exempts_nothing(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Lah", level=1)
    _quiz(db, user, {topic: 0})

    assert not _rows(client, topic)["Lah"]["exempted"]
    assert _circles(client) == {"Singlish": (0, 1)}


def test_a_user_who_skipped_the_quiz_is_exempted_from_nothing(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Lah", level=1)

    assert not _rows(client, topic)["Lah"]["exempted"]
    assert _circles(client) == {"Singlish": (0, 1)}


def test_drafts_and_withdrawn_lessons_are_never_counted(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Published", level=1)
    _lesson(db, topic, "Draft", level=1, status=LessonStatus.DRAFT)
    _lesson(db, topic, "Withdrawn", level=1, status=LessonStatus.WITHDRAWN)
    _quiz(db, user, {topic: 5})

    assert _circles(client) == {"Singlish": (1, 1)}
    assert list(_rows(client, topic)) == ["Published"]


# --- AC2: an exemption applies only to its own topic -------------------------------------


def test_an_exemption_does_not_reach_another_topic(client, db, make_user):
    user = _sign_in(client, make_user)
    singlish = _topic(db, "Singlish", position=0)
    hawker = _topic(db, "Hawker culture", position=1)
    _lesson(db, singlish, "Lah", level=1)
    _lesson(db, hawker, "Chope", level=1)
    _quiz(db, user, {singlish: 3})

    assert _circles(client) == {"Singlish": (1, 1), "Hawker culture": (0, 1)}
    assert not _rows(client, hawker)["Chope"]["exempted"]


def test_another_users_exemption_is_not_counted(client, db, make_user):
    other = make_user(**OTHER)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Lah", level=1)
    _quiz(db, other, {topic: 5})
    _sign_in(client, make_user)

    assert _circles(client) == {"Singlish": (0, 1)}
    assert not _rows(client, topic)["Lah"]["exempted"]


# --- AC3: a lesson published later at an exempted level is exempted too ------------------


def test_a_lesson_published_later_is_exempted_too(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Lah", level=1)
    _quiz(db, user, {topic: 2})
    assert _circles(client) == {"Singlish": (1, 1)}

    _lesson(db, topic, "Leh", level=2, position=1)
    _lesson(db, topic, "Lor", level=3, position=2)

    assert _circles(client) == {"Singlish": (2, 3)}
    assert _rows(client, topic)["Leh"]["exempted"]


# --- AC4: every published lesson is listed, lowest level first ---------------------------


def test_every_lesson_is_listed_lowest_level_first(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Hard", level=4, position=0)
    _lesson(db, topic, "Easy B", level=1, position=2)
    _lesson(db, topic, "Medium", level=2, position=1)
    _lesson(db, topic, "Easy A", level=1, position=3)
    _quiz(db, user, {topic: 1})

    lessons = client.get(f"/api/topics/{topic.id}").json()["lessons"]
    # Within a level, the order administrators set.
    assert [lesson["title"] for lesson in lessons] == ["Easy B", "Easy A", "Medium", "Hard"]
    assert [lesson["level"] for lesson in lessons] == [1, 1, 2, 4]


# --- AC5 to AC7: labelled until completed, opens like any other --------------------------


def test_an_exempted_lesson_not_completed_is_labelled(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Lah", level=1)
    _quiz(db, user, {topic: 1})

    row = _rows(client, topic)["Lah"]
    assert row["exempted"] is True
    assert row["completed"] is False
    assert row["best_correct"] is None
    assert row["last_attempted_at"] is None


def test_an_exempted_lesson_opens_and_can_be_answered(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Lah", level=1)
    _quiz(db, user, {topic: 1})

    assert client.get(f"/api/lessons/{lesson.id}").status_code == 200
    attempt = client.post(f"/api/lessons/{lesson.id}/attempts", json={"version": 1})
    assert attempt.status_code == 201
    attempt_id = attempt.json()["id"]
    checked = client.post(
        f"/api/attempts/{attempt_id}/answers", json={"question_id": "q1", "option_id": "right"}
    )
    assert checked.status_code == 200
    assert client.post(f"/api/attempts/{attempt_id}/finish").status_code == 200

    # AC7: now completed with its score, no longer labelled.
    row = _rows(client, topic)["Lah"]
    assert row["completed"] is True
    assert row["exempted"] is False
    assert (row["best_correct"], row["best_scored"]) == (1, 1)
    assert row["last_attempted_at"] is not None


# --- AC8 and AC9: exempted lessons count as completed, each once -------------------------


def test_a_lesson_both_exempted_and_completed_counts_once(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    lah = _lesson(db, topic, "Lah", level=1)
    _lesson(db, topic, "Leh", level=1, position=1)
    _lesson(db, topic, "Lor", level=3, position=2)
    _quiz(db, user, {topic: 1})
    _complete(db, user, lah)

    assert _circles(client) == {"Singlish": (2, 3)}
    body = client.get(f"/api/topics/{topic.id}").json()
    assert (body["completed"], body["available"]) == (2, 3)


def test_completed_and_exempted_lessons_add_up_overall(client, db, make_user):
    user = _sign_in(client, make_user)
    singlish = _topic(db, "Singlish", position=0)
    hawker = _topic(db, "Hawker culture", position=1)
    _lesson(db, singlish, "Lah", level=1)
    _lesson(db, singlish, "Lor", level=4, position=1)
    chope = _lesson(db, hawker, "Chope", level=1)
    _lesson(db, hawker, "Tray return", level=2, position=1)
    _quiz(db, user, {singlish: 2})
    _complete(db, user, chope)

    body = client.get("/api/progress").json()
    assert (body["completed"], body["available"]) == (2, 4)


def test_the_topic_page_figure_matches_its_circle(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    for level in (1, 2, 3, 4):
        _lesson(db, topic, f"Level {level}", level=level, position=level)
    _quiz(db, user, {topic: 3})

    body = client.get(f"/api/topics/{topic.id}").json()
    assert (body["completed"], body["available"]) == _circles(client)["Singlish"] == (3, 4)


def test_exempted_from_every_lesson_fills_the_circle(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Lah", level=1)
    _lesson(db, topic, "Leh", level=2, position=1)
    _quiz(db, user, {topic: 5})

    assert _circles(client) == {"Singlish": (2, 2)}
