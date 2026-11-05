"""SCRUM-53 and SCRUM-54: opening a topic lists its published lessons, each marked completed
or not, with when it was last attempted and the best score. SCRUM-86: and its description.

The list follows the same counting rules as the landing page circles (SCRUM-16 AC8), so
the figure on the topic page always matches the circle that led there.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models import (
    AptitudeAttempt,
    Lesson,
    LessonAttempt,
    LessonCompletion,
    LessonStatus,
    LessonVersion,
    Topic,
    TopicExemption,
)

USER = {"email": "user@example.com", "password": "Password123"}
OTHER = {"email": "other@example.com", "password": "Password123"}


def _doc(scored: int = 1, words: int = 0) -> dict:
    cards = [{"id": "intro", "text": " ".join(["word"] * words) or "Hello."}]
    for n in range(scored):
        cards.append(
            {
                "id": f"c{n}",
                "text": "Pick {{blank}}.",
                "question": {
                    "id": f"q{n}",
                    "options": [
                        {"id": "right", "text": "Right", "correct": True},
                        {"id": "wrong", "text": "Wrong"},
                    ],
                    "explanation": "Because.",
                },
            }
        )
    return {"cards": cards}


def _topic(db, name: str = "Singlish", archived: bool = False, description: str = "") -> Topic:
    topic = Topic(
        name=name, description=description, archived_at=datetime.now(UTC) if archived else None
    )
    db.add(topic)
    db.commit()
    return topic


def _lesson(
    db,
    topic: Topic,
    title: str,
    position: int = 0,
    status: LessonStatus = LessonStatus.PUBLISHED,
    doc: dict | None = None,
    level: int = 1,
) -> Lesson:
    lesson = Lesson(title=title, topic=topic, position=position, status=status, level=level)
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
                doc=doc or _doc(),
                published_at=now,
            )
        )
    db.commit()
    return lesson


def _complete(db, user, lesson: Lesson, correct: int = 1, scored: int = 1) -> None:
    db.add(
        LessonCompletion(
            user_id=user.id, lesson_id=lesson.id, best_correct=correct, best_scored=scored
        )
    )
    db.commit()


def _exempt(db, user, topic: Topic, level: int) -> None:
    db.add(AptitudeAttempt(user_id=user.id, results=[]))
    db.flush()
    db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=level))
    db.commit()


def _sign_in(client, make_user):
    user = make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    return user


def test_needs_a_signed_in_user(client, db):
    topic = _topic(db)
    response = client.get(f"/api/topics/{topic.id}")
    assert response.status_code == 401


def test_an_unknown_topic_is_unavailable(client, make_user):
    _sign_in(client, make_user)
    response = client.get(f"/api/topics/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_unavailable"


def test_an_archived_topic_is_unavailable(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db, archived=True)
    _lesson(db, topic, "Lah")
    response = client.get(f"/api/topics/{topic.id}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_unavailable"


def test_lists_published_lessons_in_the_order_administrators_set(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    _lesson(db, topic, "Third", position=2)
    _lesson(db, topic, "First", position=0)
    _lesson(db, topic, "Second", position=1)
    _lesson(db, topic, "A draft", position=3, status=LessonStatus.DRAFT)
    _lesson(db, topic, "Withdrawn", position=4, status=LessonStatus.WITHDRAWN)

    body = client.get(f"/api/topics/{topic.id}").json()

    assert body["name"] == "Singlish"
    assert [lesson["title"] for lesson in body["lessons"]] == ["First", "Second", "Third"]
    assert body["lessons"][0]["summary"] == "About First"


def test_a_topic_with_no_published_lessons_is_empty_not_missing(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    _lesson(db, topic, "A draft", status=LessonStatus.DRAFT)

    response = client.get(f"/api/topics/{topic.id}")

    assert response.status_code == 200
    assert response.json() | {"id": None} == {
        "id": None,
        "name": "Singlish",
        "description": "",
        "completed": 0,
        "exempted": 0,
        "available": 0,
        "lessons": [],
    }


def test_includes_the_topics_description(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db, description="The little words you will hear every day.")
    _lesson(db, topic, "Lah")

    body = client.get(f"/api/topics/{topic.id}").json()

    assert body["description"] == "The little words you will hear every day."


def test_marks_completed_lessons_and_counts_them(client, db, make_user):
    user = _sign_in(client, make_user)
    other = make_user(**OTHER)
    topic = _topic(db)
    done = _lesson(db, topic, "Done", position=0)
    open_lesson = _lesson(db, topic, "Open", position=1)
    withdrawn = _lesson(db, topic, "Withdrawn", position=2, status=LessonStatus.WITHDRAWN)
    _complete(db, user, done, correct=0, scored=1)
    _complete(db, user, withdrawn)
    # Someone else's completion never shows on this user's list.
    _complete(db, other, open_lesson)

    body = client.get(f"/api/topics/{topic.id}").json()

    assert (body["completed"], body["available"]) == (1, 2)
    first, second = body["lessons"]
    assert (first["completed"], first["best_correct"], first["best_scored"]) == (True, 0, 1)
    assert (second["completed"], second["best_correct"], second["best_scored"]) == (
        False,
        None,
        None,
    )


def test_marks_lower_level_lessons_exempted_and_counts_them(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db)
    _lesson(db, topic, "Intro", position=0, level=1)
    _lesson(db, topic, "Intermediate", position=1, level=2)
    _lesson(db, topic, "Advanced", position=2, level=3)
    _exempt(db, user, topic, level=2)

    body = client.get(f"/api/topics/{topic.id}").json()
    assert (body["completed"], body["exempted"], body["available"]) == (2, 2, 3)
    assert [(lesson["level"], lesson["exempted"]) for lesson in body["lessons"]] == [
        (1, True),
        (2, True),
        (3, False),
    ]


def test_figures_match_the_topics_circle(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db)
    lessons = [_lesson(db, topic, f"Lesson {n}", position=n) for n in range(3)]
    _complete(db, user, lessons[1])

    body = client.get(f"/api/topics/{topic.id}").json()
    (circle,) = client.get("/api/progress").json()["topics"]

    assert (body["completed"], body["available"]) == (circle["completed"], circle["available"])


def test_reading_time_and_questions_come_from_the_latest_version(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    lesson = _lesson(db, topic, "Kopi", doc=_doc(scored=1))
    db.add(
        LessonVersion(
            lesson_id=lesson.id,
            number=2,
            title="Kopi, revised",
            summary="",
            doc=_doc(scored=3, words=250),
            published_at=datetime.now(UTC),
        )
    )
    db.commit()

    (item,) = client.get(f"/api/topics/{topic.id}").json()["lessons"]

    assert item["title"] == "Kopi, revised"
    assert item["questions"] == 3
    # 250 words at 200 a minute, plus the options and explanations.
    assert item["reading_seconds"] > 75


def test_one_option_taps_are_not_counted_as_questions(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    doc = _doc(scored=1)
    doc["cards"].append(
        {
            "id": "tap",
            "text": "Say {{blank}}.",
            "question": {
                "id": "tap",
                "options": [{"id": "ok", "text": "thanks"}],
                "explanation": "Polite.",
            },
        }
    )
    _lesson(db, topic, "Kopi", doc=doc)

    (item,) = client.get(f"/api/topics/{topic.id}").json()["lessons"]

    assert item["questions"] == 1


def test_never_reveals_which_option_is_right(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    _lesson(db, topic, "Kopi")

    text = client.get(f"/api/topics/{topic.id}").text

    assert 'correct"' not in text.replace("best_correct", "")
    assert "Right" not in text


# --- Last attempted and best score (SCRUM-54) -----------------------------------------------


def _run(client, lesson: Lesson, answers: dict[str, str], finish: bool = True) -> str:
    response = client.post(f"/api/lessons/{lesson.id}/attempts", json={"version": 1})
    assert response.status_code == 201, response.json()
    attempt = response.json()["id"]
    for question_id, option_id in answers.items():
        answered = client.post(
            f"/api/attempts/{attempt}/answers",
            json={"question_id": question_id, "option_id": option_id},
        )
        assert answered.status_code == 200, answered.json()
    if finish:
        assert client.post(f"/api/attempts/{attempt}/finish").status_code == 200
    return attempt


def _finished_at(db, attempt_id: str) -> datetime:
    db.expire_all()
    return db.get(LessonAttempt, uuid.UUID(attempt_id)).finished_at


def _item(client, topic: Topic) -> dict:
    (item,) = client.get(f"/api/topics/{topic.id}").json()["lessons"]
    return item


TWO_RIGHT = {"q0": "right", "q1": "right"}
ONE_RIGHT = {"q0": "right", "q1": "wrong"}


def test_not_attempted_yet_has_no_date_or_score(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    _lesson(db, topic, "Kopi", doc=_doc(scored=2))

    item = _item(client, topic)

    assert (item["last_attempted_at"], item["best_correct"], item["best_scored"]) == (
        None,
        None,
        None,
    )


def test_an_unfinished_attempt_is_not_an_attempt(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    lesson = _lesson(db, topic, "Kopi", doc=_doc(scored=2))
    _run(client, lesson, {"q0": "right"}, finish=False)

    assert _item(client, topic)["last_attempted_at"] is None


def test_finishing_records_the_date_and_score(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    lesson = _lesson(db, topic, "Kopi", doc=_doc(scored=2))
    attempt = _run(client, lesson, ONE_RIGHT)

    item = _item(client, topic)

    assert datetime.fromisoformat(item["last_attempted_at"]) == _finished_at(db, attempt)
    assert (item["best_correct"], item["best_scored"]) == (1, 2)


def test_a_worse_retake_moves_the_date_but_keeps_the_best_and_the_count(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    lesson = _lesson(db, topic, "Kopi", doc=_doc(scored=2))
    _run(client, lesson, TWO_RIGHT)
    retake = _run(client, lesson, ONE_RIGHT)

    body = client.get(f"/api/topics/{topic.id}").json()
    (item,) = body["lessons"]

    assert datetime.fromisoformat(item["last_attempted_at"]) == _finished_at(db, retake)
    assert (item["best_correct"], item["best_scored"]) == (2, 2)
    assert (body["completed"], body["available"]) == (1, 1)


def test_a_better_retake_raises_the_best(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    lesson = _lesson(db, topic, "Kopi", doc=_doc(scored=2))
    _run(client, lesson, ONE_RIGHT)
    _run(client, lesson, TWO_RIGHT)

    item = _item(client, topic)

    assert (item["best_correct"], item["best_scored"]) == (2, 2)


def test_a_completion_without_attempts_uses_its_completion_time(client, db, make_user):
    user = _sign_in(client, make_user)
    topic = _topic(db)
    lesson = _lesson(db, topic, "Kopi")
    _complete(db, user, lesson)
    completion = db.scalar(select(LessonCompletion).where(LessonCompletion.lesson_id == lesson.id))

    item = _item(client, topic)

    assert datetime.fromisoformat(item["last_attempted_at"]) == completion.completed_at


def test_another_users_attempts_are_not_counted(client, db, make_user):
    make_user(**OTHER)
    client.post("/api/auth/sign-in", json=OTHER)
    topic = _topic(db)
    lesson = _lesson(db, topic, "Kopi", doc=_doc(scored=2))
    _run(client, lesson, TWO_RIGHT)
    client.post("/api/auth/sign-out")
    _sign_in(client, make_user)

    assert _item(client, topic)["last_attempted_at"] is None
