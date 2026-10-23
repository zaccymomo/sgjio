"""SCRUM-15 and SCRUM-16: a learner reads a lesson, answers its questions on the server, and
finishing records completion and the best score."""

import random
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app import learning
from app.models import AttemptAnswer, Lesson, LessonCompletion, LessonStatus, LessonVersion, Topic

USER = {"email": "user@example.com", "password": "Password123"}
OTHER = {"email": "other@example.com", "password": "Password123"}

DOC = {
    "cards": [
        {"id": "intro", "text": "**Kopi** is coffee with condensed milk."},
        {
            "id": "c1",
            "text": "Black coffee with sugar is kopi {{blank}}.",
            "question": {
                "id": "q1",
                "options": [
                    {"id": "o", "text": "O", "correct": True},
                    {"id": "c", "text": "C", "why_not": "C means evaporated milk."},
                    {"id": "siew", "text": "Siew dai"},
                ],
                "explanation": "O means no milk.",
            },
        },
        {
            "id": "c2",
            "text": "Less sugar is {{blank}}.",
            "question": {
                "id": "q2",
                "options": [
                    {"id": "dai", "text": "Siew dai", "correct": True},
                    {"id": "gao", "text": "Gao"},
                ],
                "explanation": "Siew dai means less sweet.",
                "shuffle": False,
            },
        },
        {
            "id": "c3",
            "text": "Say {{blank}} to finish.",
            # A one-option tap: answered, but never scored.
            "question": {
                "id": "tap",
                "options": [{"id": "ok", "text": "thank you"}],
                "explanation": "Politeness.",
            },
        },
    ]
}


def _topic(db, name="Hawker & Food") -> Topic:
    topic = Topic(name=name)
    db.add(topic)
    db.commit()
    return topic


def _publish(db, lesson: Lesson, doc=DOC, title="Ordering kopi") -> LessonVersion:
    number = len(lesson.versions) + 1
    version = LessonVersion(
        lesson_id=lesson.id,
        number=number,
        title=title,
        summary="",
        doc=doc,
        published_at=datetime.now(UTC),
    )
    lesson.status = LessonStatus.PUBLISHED
    lesson.published_at = version.published_at
    db.add(version)
    db.commit()
    db.refresh(lesson)
    return version


@pytest.fixture
def lesson(db) -> Lesson:
    lesson = Lesson(title="Ordering kopi", topic=_topic(db), draft=DOC)
    db.add(lesson)
    db.commit()
    _publish(db, lesson)
    return lesson


@pytest.fixture
def learner(client, make_user):
    make_user(**USER)
    assert client.post("/api/auth/sign-in", json=USER).status_code == 200
    return client


def _start(client, lesson, version=1) -> str:
    response = client.post(f"/api/lessons/{lesson.id}/attempts", json={"version": version})
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def _answer(client, attempt_id, question_id, option_id):
    return client.post(
        f"/api/attempts/{attempt_id}/answers",
        json={"question_id": question_id, "option_id": option_id},
    )


def _run(client, lesson, answers: dict[str, str]) -> dict:
    attempt = _start(client, lesson)
    for question_id, option_id in answers.items():
        assert _answer(client, attempt, question_id, option_id).status_code == 200
    response = client.post(f"/api/attempts/{attempt}/finish")
    assert response.status_code == 200, response.json()
    return response.json()


ALL_RIGHT = {"q1": "o", "q2": "dai", "tap": "ok"}
HALF_RIGHT = {"q1": "c", "q2": "dai", "tap": "ok"}
ALL_WRONG = {"q1": "c", "q2": "gao", "tap": "ok"}


def _completion(db, lesson) -> LessonCompletion | None:
    db.expire_all()
    return db.scalar(select(LessonCompletion).where(LessonCompletion.lesson_id == lesson.id))


# --- Reading a lesson (SCRUM-15 AC1) --------------------------------------------------------


def test_lessons_need_a_signed_in_user(client, lesson):
    assert client.get(f"/api/lessons/{lesson.id}").status_code == 401


def test_a_learner_sees_title_topic_and_cards(learner, lesson):
    body = learner.get(f"/api/lessons/{lesson.id}").json()

    assert body["title"] == "Ordering kopi"
    assert body["topic"]["name"] == "Hawker & Food"
    assert body["version"] == 1
    assert [card["id"] for card in body["cards"]] == ["intro", "c1", "c2", "c3"]
    assert body["cards"][3]["question"]["scored"] is False


def test_the_learners_copy_never_says_which_option_is_right(learner, lesson):
    body = learner.get(f"/api/lessons/{lesson.id}").json()
    text = str(body)

    for card in body["cards"]:
        for option in (card["question"] or {}).get("options", []):
            assert set(option) == {"id", "text"}
    assert "explanation" not in text
    assert "why_not" not in text
    assert "O means no milk" not in text


def test_options_are_shuffled_unless_the_lesson_says_not(db, lesson):
    orders = {
        tuple(
            o["id"]
            for o in learning.learner_lesson(db, lesson.id, random.Random(seed)).cards[1][
                "question"
            ]["options"]
        )
        for seed in range(20)
    }
    fixed = {
        tuple(
            o["id"]
            for o in learning.learner_lesson(db, lesson.id, random.Random(seed)).cards[2][
                "question"
            ]["options"]
        )
        for seed in range(20)
    }
    assert len(orders) > 1
    assert fixed == {("dai", "gao")}


def test_learners_see_the_newest_version(learner, db, lesson):
    changed = {**DOC, "cards": DOC["cards"][1:]}
    _publish(db, lesson, changed, title="Ordering kopi, revised")

    body = learner.get(f"/api/lessons/{lesson.id}").json()
    assert body["version"] == 2
    assert body["title"] == "Ordering kopi, revised"
    assert len(body["cards"]) == 3


@pytest.mark.parametrize("status", [LessonStatus.DRAFT, LessonStatus.WITHDRAWN])
def test_unpublished_lessons_are_unavailable(learner, db, lesson, status):
    lesson.status = status
    db.commit()

    response = learner.get(f"/api/lessons/{lesson.id}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "lesson_unavailable"


def test_lessons_in_an_archived_topic_are_unavailable(learner, db, lesson):
    lesson.topic.archived_at = datetime.now(UTC)
    db.commit()

    assert learner.get(f"/api/lessons/{lesson.id}").status_code == 404


# --- Checking answers (SCRUM-16 AC1, AC2, AC6) ---------------------------------------------


def test_a_right_answer_is_marked_right_with_its_explanation(learner, lesson):
    attempt = _start(learner, lesson)
    body = _answer(learner, attempt, "q1", "o").json()

    assert body == {
        "correct": True,
        "correct_option_id": "o",
        "why_not": "",
        "explanation": "O means no milk.",
    }


def test_a_wrong_answer_shows_the_right_one_and_why_not(learner, lesson):
    attempt = _start(learner, lesson)
    body = _answer(learner, attempt, "q1", "c").json()

    assert body["correct"] is False
    assert body["correct_option_id"] == "o"
    assert body["why_not"] == "C means evaporated milk."
    assert body["explanation"] == "O means no milk."


def test_an_option_from_another_question_is_refused(learner, db, lesson):
    attempt = _start(learner, lesson)
    response = _answer(learner, attempt, "q1", "dai")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "option_not_found"
    assert db.scalar(select(func.count()).select_from(AttemptAnswer)) == 0


def test_an_unknown_question_is_refused(learner, lesson):
    attempt = _start(learner, lesson)
    response = _answer(learner, attempt, "nope", "o")
    assert response.json()["detail"]["code"] == "question_not_found"


def test_answers_to_a_withdrawn_lesson_are_refused(learner, db, lesson):
    attempt = _start(learner, lesson)
    lesson.status = LessonStatus.WITHDRAWN
    db.commit()

    response = _answer(learner, attempt, "q1", "o")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "lesson_unavailable"
    assert db.scalar(select(func.count()).select_from(AttemptAnswer)) == 0


def test_only_the_first_answer_to_a_question_counts(learner, db, lesson):
    attempt = _start(learner, lesson)
    first = _answer(learner, attempt, "q1", "c").json()
    again = _answer(learner, attempt, "q1", "c").json()
    changed = _answer(learner, attempt, "q1", "o").json()

    assert first == again == changed
    assert changed["correct"] is False
    assert db.scalar(select(func.count()).select_from(AttemptAnswer)) == 1


def test_a_learner_cannot_use_someone_elses_attempt(learner, make_user, lesson):
    attempt = _start(learner, lesson)
    make_user(**OTHER)
    learner.post("/api/auth/sign-in", json=OTHER)

    response = _answer(learner, attempt, "q1", "o")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "attempt_not_found"
    assert learner.post(f"/api/attempts/{attempt}/finish").status_code == 404


def test_starting_with_an_old_version_asks_for_a_reload(learner, db, lesson):
    _publish(db, lesson)

    response = learner.post(f"/api/lessons/{lesson.id}/attempts", json={"version": 1})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_updated"


def test_an_attempt_keeps_the_version_it_started_with(learner, db, lesson):
    attempt = _start(learner, lesson)
    _publish(db, lesson, {"cards": [DOC["cards"][2]]})

    # q1 is gone from version 2, but this attempt was shown version 1.
    assert _answer(learner, attempt, "q1", "o").json()["correct"] is True


# --- Finishing (SCRUM-16 AC3-AC6, SCRUM-15 AC4) --------------------------------------------


def test_leaving_before_the_end_completes_nothing(learner, db, lesson):
    attempt = _start(learner, lesson)
    _answer(learner, attempt, "q1", "o")

    assert _completion(db, lesson) is None
    assert learner.get("/api/progress").json()["completed"] == 0


def test_finishing_needs_every_question_answered(learner, db, lesson):
    attempt = _start(learner, lesson)
    _answer(learner, attempt, "q1", "o")

    response = learner.post(f"/api/attempts/{attempt}/finish")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "questions_unanswered"
    assert response.json()["detail"]["question_ids"] == ["q2", "tap"]
    assert _completion(db, lesson) is None


def test_finishing_completes_the_lesson_even_with_every_answer_wrong(learner, db, lesson):
    body = _run(learner, lesson, ALL_WRONG)

    assert body["score"] == {"correct": 0, "scored": 2}
    assert body["first_completion"] is True
    assert _completion(db, lesson).best_correct == 0
    assert learner.get("/api/progress").json()["completed"] == 1


def test_taps_are_left_out_of_the_score(learner, lesson):
    assert _run(learner, lesson, ALL_RIGHT)["score"] == {"correct": 2, "scored": 2}


def test_a_retake_never_lowers_the_best_score(learner, db, lesson):
    _run(learner, lesson, ALL_RIGHT)
    body = _run(learner, lesson, ALL_WRONG)

    assert body["score"] == {"correct": 0, "scored": 2}
    assert body["best"] == {"correct": 2, "scored": 2}
    assert body["first_completion"] is False
    completion = _completion(db, lesson)
    assert completion.mastered
    assert learner.get("/api/progress").json()["completed"] == 1


def test_a_better_retake_raises_the_best_score(learner, db, lesson):
    _run(learner, lesson, ALL_WRONG)
    body = _run(learner, lesson, HALF_RIGHT)

    assert body["best"] == {"correct": 1, "scored": 2}
    assert db.scalar(select(func.count()).select_from(LessonCompletion)) == 1


def test_best_score_compares_percentages_and_a_tie_keeps_the_latest(learner, db, lesson):
    first = _run(learner, lesson, HALF_RIGHT)
    # Version 2 has one scored question: 1 of 1 beats 1 of 2.
    _publish(db, lesson, {"cards": DOC["cards"][1:2]})
    attempt = _start(learner, lesson, version=2)
    _answer(learner, attempt, "q1", "o")
    better = learner.post(f"/api/attempts/{attempt}/finish").json()
    assert better["best"] == {"correct": 1, "scored": 1}

    # Another 1 of 1 ties, and the newer attempt becomes the best.
    attempt = _start(learner, lesson, version=2)
    _answer(learner, attempt, "q1", "o")
    tie = learner.post(f"/api/attempts/{attempt}/finish").json()
    assert _completion(db, lesson).best_attempt_id is not None
    assert str(_completion(db, lesson).best_attempt_id) == tie["attempt_id"]
    assert first["attempt_id"] != tie["attempt_id"]


def test_finishing_twice_records_once(learner, db, lesson):
    attempt = _start(learner, lesson)
    for question_id, option_id in ALL_RIGHT.items():
        _answer(learner, attempt, question_id, option_id)

    first = learner.post(f"/api/attempts/{attempt}/finish").json()
    second = learner.post(f"/api/attempts/{attempt}/finish").json()

    assert first["first_completion"] is True
    assert second["first_completion"] is False
    assert second["score"] == first["score"]
    assert db.scalar(select(func.count()).select_from(LessonCompletion)) == 1


def test_a_finished_attempt_takes_no_more_answers(learner, lesson):
    attempt = _start(learner, lesson)
    for question_id, option_id in ALL_RIGHT.items():
        _answer(learner, attempt, question_id, option_id)
    learner.post(f"/api/attempts/{attempt}/finish")

    response = _answer(learner, attempt, "q1", "c")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "attempt_finished"


def test_a_completion_survives_withdrawal_but_leaves_the_figures(learner, db, lesson):
    _run(learner, lesson, ALL_RIGHT)
    lesson.status = LessonStatus.WITHDRAWN
    db.commit()

    assert _completion(db, lesson) is not None
    assert learner.get("/api/progress").json() == {
        "topics": [],
        "completed": 0,
        "available": 0,
        "suggestion": None,
    }
