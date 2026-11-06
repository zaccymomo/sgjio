"""SCRUM-44: reviewing the questions a learner answered wrongly, each with its right answer,
its explanation and the lesson it came from. (Ported from api/tests/test_review.py.)"""

import pytest

from tests.conftest import sign_in

DOC = {
    "cards": [
        {
            "id": "c1",
            "text": "Black coffee with sugar is kopi {{blank}}.",
            "question": {
                "id": "q1",
                "options": [
                    {"id": "o", "text": "O", "correct": True},
                    {"id": "c", "text": "C", "why_not": "C means evaporated milk."},
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
            },
        },
        {
            "id": "c3",
            "text": "Say {{blank}}.",
            "question": {
                "id": "tap",
                "options": [{"id": "ok", "text": "thank you"}],
                "explanation": "Politeness.",
            },
        },
    ]
}


@pytest.fixture
def topic(content):
    return content.topic("Hawker & Food")


@pytest.fixture
def lesson(content, topic):
    return content.lesson(topic, "Ordering kopi", doc=DOC)


@pytest.fixture
def learner(client, make_user):
    return sign_in(client, make_user("user@example.com"))


def _attempt(client, lesson, answers: dict[str, str], finish=True, version=None) -> str:
    version = version or len(lesson.versions)
    response = client.post(f"/api/lessons/{lesson.id}/attempts", json={"version": version})
    attempt = response.json()["id"]
    for question_id, option_id in answers.items():
        response = client.post(
            f"/api/attempts/{attempt}/answers",
            json={"question_id": question_id, "option_id": option_id},
        )
        assert response.status_code == 200
    if finish:
        assert client.post(f"/api/attempts/{attempt}/finish").status_code == 200
    return attempt


def _mistakes(client) -> list[dict]:
    response = client.get("/api/review")
    assert response.status_code == 200
    return response.json()["mistakes"]


def test_review_needs_a_signed_in_user(client):
    assert client.get("/api/review").status_code == 401


def test_only_the_questions_answered_wrongly_are_listed(learner, lesson):
    """AC1: one wrong, one right, and the unscored tap never counts."""
    _attempt(learner, lesson, {"q1": "c", "q2": "dai", "tap": "ok"})

    assert [m["question_id"] for m in _mistakes(learner)] == ["q1"]


def test_a_mistake_shows_the_right_answer_and_why(learner, lesson):
    """AC2 and AC3: the answer chosen, the right one, the explanation and the lesson."""
    _attempt(learner, lesson, {"q1": "c", "q2": "dai", "tap": "ok"})

    [mistake] = _mistakes(learner)
    assert mistake == {
        "lesson_id": str(lesson.id),
        "lesson_title": "Ordering kopi",
        "topic_name": "Hawker & Food",
        "question_id": "q1",
        "text": "Black coffee with sugar is kopi {{blank}}.",
        "chosen": "C",
        "correct": "O",
        "explanation": "O means no milk.",
        "why_not": "C means evaporated milk.",
        "answered_at": mistake["answered_at"],
    }


def test_nothing_to_review_is_an_empty_list(learner, lesson):
    """AC4: the page says there is nothing to review."""
    assert _mistakes(learner) == []
    _attempt(learner, lesson, {"q1": "o", "q2": "dai", "tap": "ok"})
    assert _mistakes(learner) == []


def test_getting_it_right_on_a_retake_takes_it_off_the_list(learner, lesson):
    _attempt(learner, lesson, {"q1": "c", "q2": "gao", "tap": "ok"})
    _attempt(learner, lesson, {"q1": "o", "q2": "gao", "tap": "ok"})

    assert [m["question_id"] for m in _mistakes(learner)] == ["q2"]


def test_getting_it_wrong_again_puts_it_back(learner, lesson):
    _attempt(learner, lesson, {"q1": "c", "q2": "dai", "tap": "ok"})
    _attempt(learner, lesson, {"q1": "o", "q2": "dai", "tap": "ok"})
    _attempt(learner, lesson, {"q1": "c", "q2": "dai", "tap": "ok"})

    assert [m["question_id"] for m in _mistakes(learner)] == ["q1"]


def test_answers_in_an_unfinished_attempt_count(learner, lesson):
    _attempt(learner, lesson, {"q1": "c"}, finish=False)

    assert [m["question_id"] for m in _mistakes(learner)] == ["q1"]


def test_newest_mistakes_come_first(learner, lesson):
    attempt = _attempt(learner, lesson, {"q2": "gao"}, finish=False)
    learner.post(f"/api/attempts/{attempt}/answers", json={"question_id": "q1", "option_id": "c"})

    assert [m["question_id"] for m in _mistakes(learner)] == ["q1", "q2"]


def test_mistakes_are_the_users_own(client, make_user, learner, lesson):
    _attempt(learner, lesson, {"q1": "c", "q2": "dai", "tap": "ok"})
    sign_in(client, make_user("other@example.com"))

    assert _mistakes(client) == []


def test_a_withdrawn_lesson_or_archived_topic_drops_out(learner, content, lesson, topic):
    """Every mistake leads to a lesson the learner can open (AC3)."""
    _attempt(learner, lesson, {"q1": "c", "q2": "dai", "tap": "ok"})

    content.withdraw(lesson)
    assert _mistakes(learner) == []

    content.restore(lesson)
    content.archive(topic)
    assert _mistakes(learner) == []


def test_a_mistake_reads_as_the_lesson_does_now(learner, content, lesson):
    """A revised explanation shows; a question since removed is no longer a mistake."""
    _attempt(learner, lesson, {"q1": "c", "q2": "gao", "tap": "ok"})
    revised = {"cards": [dict(DOC["cards"][0])]}
    revised["cards"][0]["question"] = {
        **DOC["cards"][0]["question"],
        "explanation": "Kopi O has no milk at all.",
    }
    content.publish(lesson, revised, title="Ordering kopi, revised")

    [mistake] = _mistakes(learner)
    assert mistake["question_id"] == "q1"
    assert mistake["lesson_title"] == "Ordering kopi, revised"
    assert mistake["explanation"] == "Kopi O has no milk at all."


def test_an_option_since_removed_still_says_what_was_chosen(learner, content, lesson):
    _attempt(learner, lesson, {"q1": "c", "q2": "dai", "tap": "ok"})
    question = {
        **DOC["cards"][0]["question"],
        "options": [
            {"id": "o", "text": "O", "correct": True},
            {"id": "peng", "text": "Peng"},
        ],
    }
    content.publish(lesson, {"cards": [{**DOC["cards"][0], "question": question}]})

    [mistake] = _mistakes(learner)
    assert (mistake["chosen"], mistake["correct"], mistake["why_not"]) == ("C", "O", "")


def test_a_choice_that_has_become_the_right_answer_is_not_a_mistake(learner, content, lesson):
    _attempt(learner, lesson, {"q1": "c", "q2": "dai", "tap": "ok"})
    question = {
        **DOC["cards"][0]["question"],
        "options": [
            {"id": "o", "text": "O"},
            {"id": "c", "text": "C", "correct": True},
        ],
    }
    content.publish(lesson, {"cards": [{**DOC["cards"][0], "question": question}]})

    assert _mistakes(learner) == []
