"""SCRUM-53 and SCRUM-54: opening a topic lists its published lessons, each marked completed
or not, with when it was last attempted and the best score. SCRUM-86: and its description.
(Ported from api/tests/test_topic_lessons.py.)

The list follows the same counting rules as the landing page circles (SCRUM-16 AC8), so
the figure on the topic page always matches the circle that led there.
"""

import uuid
from datetime import datetime

import pytest

from app.models import LessonAttempt
from tests.conftest import sign_in, sign_out
from tests.support.records import complete, quiz


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


@pytest.fixture
def lesson_in(content):
    def _lesson(topic, title, position=0, status="published", doc=None, level=1):
        return content.lesson(
            topic,
            title,
            position=position,
            status=status,
            doc=doc or _doc(),
            level=level,
            summary=f"About {title}",
        )

    return _lesson


def _sign_in(client, make_user):
    user = make_user("user@example.com")
    sign_in(client, user)
    return user


def test_needs_a_signed_in_user(client, content):
    topic = content.topic()
    assert client.get(f"/api/topics/{topic.id}").status_code == 401


def test_an_unknown_topic_is_unavailable(client, make_user):
    _sign_in(client, make_user)
    response = client.get(f"/api/topics/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "topic_unavailable",
        "message": "This topic isn't available any more. It may have been removed.",
    }


def test_an_archived_topic_is_unavailable(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic = content.topic(archived=True)
    lesson_in(topic, "Lah")
    response = client.get(f"/api/topics/{topic.id}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_unavailable"


def test_a_deleted_topic_is_unavailable(client, content, make_user):
    _sign_in(client, make_user)
    topic = content.topic("Short-lived")
    content.delete_topic(topic)
    assert client.get(f"/api/topics/{topic.id}").status_code == 404


def test_lists_published_lessons_in_the_order_administrators_set(
    client, content, lesson_in, make_user
):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson_in(topic, "Third", position=2)
    lesson_in(topic, "First", position=0)
    lesson_in(topic, "Second", position=1)
    lesson_in(topic, "A draft", position=3, status="draft")
    lesson_in(topic, "Withdrawn", position=4, status="withdrawn")

    body = client.get(f"/api/topics/{topic.id}").json()
    assert body["name"] == "Singlish"
    assert [lesson["title"] for lesson in body["lessons"]] == ["First", "Second", "Third"]
    assert body["lessons"][0]["summary"] == "About First"


def test_a_reorder_or_move_takes_effect(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic, other = content.topic(), content.topic("Hawker", 1)
    first = lesson_in(topic, "First", position=0)
    second = lesson_in(topic, "Second", position=1)
    content.update_lesson(first, position=2)
    assert [x["title"] for x in client.get(f"/api/topics/{topic.id}").json()["lessons"]] == [
        "Second",
        "First",
    ]

    content.update_lesson(second, topic=other)
    assert [x["title"] for x in client.get(f"/api/topics/{topic.id}").json()["lessons"]] == [
        "First"
    ]
    assert [x["title"] for x in client.get(f"/api/topics/{other.id}").json()["lessons"]] == [
        "Second"
    ]


def test_a_topic_with_no_published_lessons_is_empty_not_missing(
    client, content, lesson_in, make_user
):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson_in(topic, "A draft", status="draft")

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


def test_includes_the_topics_description(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic = content.topic(description="The little words you will hear every day.")
    lesson_in(topic, "Lah")

    body = client.get(f"/api/topics/{topic.id}").json()

    assert body["description"] == "The little words you will hear every day."


def test_a_renamed_or_described_topic_shows_its_new_name(client, content, make_user):
    _sign_in(client, make_user)
    topic = content.topic()
    content.update_topic(topic, name="Singlish 101", description="Now described.")

    body = client.get(f"/api/topics/{topic.id}").json()
    assert (body["name"], body["description"]) == ("Singlish 101", "Now described.")


def test_marks_completed_lessons_and_counts_them(client, db, content, lesson_in, make_user):
    user = _sign_in(client, make_user)
    other = make_user("other@example.com")
    topic = content.topic()
    done = lesson_in(topic, "Done", position=0)
    open_lesson = lesson_in(topic, "Open", position=1)
    withdrawn = lesson_in(topic, "Withdrawn", position=2, status="withdrawn")
    complete(db, user, done, correct=0, scored=1)
    complete(db, user, withdrawn)
    # Someone else's completion never shows on this user's list.
    complete(db, other, open_lesson)

    body = client.get(f"/api/topics/{topic.id}").json()

    assert (body["completed"], body["available"]) == (1, 2)
    first, second = body["lessons"]
    assert (first["completed"], first["best_correct"], first["best_scored"]) == (True, 0, 1)
    assert (second["completed"], second["best_correct"], second["best_scored"]) == (
        False,
        None,
        None,
    )


def test_marks_lower_level_lessons_exempted_and_counts_them(
    client, db, content, lesson_in, make_user
):
    user = _sign_in(client, make_user)
    topic = content.topic()
    lesson_in(topic, "Intro", position=0, level=1)
    lesson_in(topic, "Intermediate", position=1, level=2)
    lesson_in(topic, "Advanced", position=2, level=3)
    quiz(db, user, {topic: 2})

    body = client.get(f"/api/topics/{topic.id}").json()
    assert (body["completed"], body["exempted"], body["available"]) == (2, 2, 3)
    assert [(lesson["level"], lesson["exempted"]) for lesson in body["lessons"]] == [
        (1, True),
        (2, True),
        (3, False),
    ]


def test_figures_match_the_topics_circle(client, db, content, lesson_in, make_user):
    user = _sign_in(client, make_user)
    topic = content.topic()
    lessons = [lesson_in(topic, f"Lesson {n}", position=n) for n in range(3)]
    complete(db, user, lessons[1])

    body = client.get(f"/api/topics/{topic.id}").json()
    (circle,) = client.get("/api/progress").json()["topics"]

    assert (body["completed"], body["available"]) == (circle["completed"], circle["available"])


def test_reading_time_and_questions_come_from_the_latest_version(
    client, content, lesson_in, make_user
):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson = lesson_in(topic, "Kopi", doc=_doc(scored=1))
    content.publish(lesson, _doc(scored=3, words=250), title="Kopi, revised")

    (item,) = client.get(f"/api/topics/{topic.id}").json()["lessons"]

    assert item["title"] == "Kopi, revised"
    assert item["questions"] == 3
    # 250 words at 200 a minute, plus the options and explanations.
    assert item["reading_seconds"] > 75


def test_one_option_taps_are_not_counted_as_questions(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic = content.topic()
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
    lesson_in(topic, "Kopi", doc=doc)

    (item,) = client.get(f"/api/topics/{topic.id}").json()["lessons"]

    assert item["questions"] == 1


def test_never_reveals_which_option_is_right(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson_in(topic, "Kopi")

    text = client.get(f"/api/topics/{topic.id}").text

    assert 'correct"' not in text.replace("best_correct", "")
    assert "Right" not in text


# --- Last attempted and best score (SCRUM-54) -----------------------------------------------


def _run(client, lesson, answers: dict[str, str], finish: bool = True) -> str:
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


def _item(client, topic) -> dict:
    (item,) = client.get(f"/api/topics/{topic.id}").json()["lessons"]
    return item


TWO_RIGHT = {"q0": "right", "q1": "right"}
ONE_RIGHT = {"q0": "right", "q1": "wrong"}


def test_not_attempted_yet_has_no_date_or_score(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson_in(topic, "Kopi", doc=_doc(scored=2))

    item = _item(client, topic)

    assert (item["last_attempted_at"], item["best_correct"], item["best_scored"]) == (
        None,
        None,
        None,
    )


def test_an_unfinished_attempt_is_not_an_attempt(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson = lesson_in(topic, "Kopi", doc=_doc(scored=2))
    _run(client, lesson, {"q0": "right"}, finish=False)

    assert _item(client, topic)["last_attempted_at"] is None


def test_finishing_records_the_date_and_score(client, db, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson = lesson_in(topic, "Kopi", doc=_doc(scored=2))
    attempt = _run(client, lesson, ONE_RIGHT)

    item = _item(client, topic)

    assert datetime.fromisoformat(item["last_attempted_at"]) == _finished_at(db, attempt)
    assert (item["best_correct"], item["best_scored"]) == (1, 2)


def test_a_worse_retake_moves_the_date_but_keeps_the_best_and_the_count(
    client, db, content, lesson_in, make_user
):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson = lesson_in(topic, "Kopi", doc=_doc(scored=2))
    _run(client, lesson, TWO_RIGHT)
    retake = _run(client, lesson, ONE_RIGHT)

    body = client.get(f"/api/topics/{topic.id}").json()
    (item,) = body["lessons"]

    assert datetime.fromisoformat(item["last_attempted_at"]) == _finished_at(db, retake)
    assert (item["best_correct"], item["best_scored"]) == (2, 2)
    assert (body["completed"], body["available"]) == (1, 1)


def test_a_better_retake_raises_the_best(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson = lesson_in(topic, "Kopi", doc=_doc(scored=2))
    _run(client, lesson, ONE_RIGHT)
    _run(client, lesson, TWO_RIGHT)

    item = _item(client, topic)

    assert (item["best_correct"], item["best_scored"]) == (2, 2)


def test_a_completion_without_attempts_uses_its_completion_time(
    client, db, content, lesson_in, make_user
):
    user = _sign_in(client, make_user)
    topic = content.topic()
    lesson = lesson_in(topic, "Kopi")
    completion = complete(db, user, lesson)
    db.refresh(completion)

    item = _item(client, topic)

    assert datetime.fromisoformat(item["last_attempted_at"]) == completion.completed_at


def test_another_users_attempts_are_not_counted(client, content, lesson_in, make_user):
    sign_in(client, make_user("other@example.com"))
    topic = content.topic()
    lesson = lesson_in(topic, "Kopi", doc=_doc(scored=2))
    _run(client, lesson, TWO_RIGHT)
    sign_out(client)
    _sign_in(client, make_user)

    assert _item(client, topic)["last_attempted_at"] is None
