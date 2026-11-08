"""SCRUM-97: the adaptive onboarding quiz. (Ported from the quiz half of
api/tests/test_aptitude.py.)

The bank is Content's: these tests build it through content.aptitude_question.changed and
content.aptitude_bank.changed, as the seed's aptitude_questions.yaml would. Moved to
Content: seeded bank readiness for administrators, creating and editing questions, exactly
one correct option, the reserved "not-sure" id, and a missing level making the bank not
ready (Learning's side of that is test_a_bank_that_is_not_ready_refuses_with_its_topics).
"""

import pytest
from sqlalchemy import select

from app.aptitude import NOT_SURE_OPTION, _quiz_options
from app.models import AptitudeAttempt, QuizQuestion, TopicExemption
from tests.conftest import sign_in

TOPICS = [
    "Singlish",
    "Hawker & Food",
    "Workplace",
    "Public Etiquette",
    "Festivals",
    "Getting Around",
]
NEWCOMER = "newcomer@sgjio.example.com"


@pytest.fixture
def bank(content):
    """The six seed topics, each with an active question at every level: a ready quiz."""
    topics = [content.topic(name, position) for position, name in enumerate(TOPICS)]
    return content.full_bank(topics)


@pytest.fixture
def newcomer(client, make_user):
    user = make_user(NEWCOMER)
    sign_in(client, user)
    return user


def _wrong(question: QuizQuestion) -> str:
    return next(
        option["id"] for option in question.options if option["id"] != question.correct_option_id
    )


def test_the_quiz_needs_a_signed_in_user(client):
    assert client.post("/api/aptitude/start").status_code == 401


def test_adaptive_quiz_moves_up_on_correct_and_topics_on_wrong(client, db, bank, newcomer):
    started = client.post("/api/aptitude/start")
    assert started.status_code == 200
    first = started.json()["question"]
    assert first["level"] == 1
    assert (first["topic"], first["topic_index"], first["topic_count"]) == ("Singlish", 1, 6)
    assert "correct_option_id" not in first

    first_model = db.get(QuizQuestion, first["id"])
    answers = [{"question_id": first["id"], "option_id": first_model.correct_option_id}]
    second = client.post("/api/aptitude/next", json={"answers": answers}).json()["question"]
    assert second["topic_id"] == first["topic_id"]
    assert second["level"] == 2

    second_model = db.get(QuizQuestion, second["id"])
    answers.append({"question_id": second["id"], "option_id": _wrong(second_model)})
    third = client.post("/api/aptitude/next", json={"answers": answers}).json()["question"]
    assert third["topic_id"] != first["topic_id"]
    assert third["level"] == 1

    current = third
    while current is not None:
        model = db.get(QuizQuestion, current["id"])
        answers.append({"question_id": current["id"], "option_id": _wrong(model)})
        step = client.post("/api/aptitude/next", json={"answers": answers}).json()
        current = step["question"]

    submitted = client.post("/api/aptitude/submit", json={"answers": answers})
    assert submitted.status_code == 200
    result = submitted.json()
    assert len(result["placements"]) == len(TOPICS)
    assert result["placements"][0]["level"] == 1
    assert all(placement["level"] == 0 for placement in result["placements"][1:])
    assert db.scalar(select(AptitudeAttempt)) is not None
    assert len(
        list(db.scalars(select(TopicExemption).where(TopicExemption.user_id == newcomer.id)))
    ) == len(TOPICS)
    refused = client.post("/api/aptitude/start")
    assert refused.status_code == 409
    assert refused.json()["detail"] == {
        "code": "quiz_already_completed",
        "message": "You have already completed the aptitude test.",
    }
    assert client.get("/api/progress").json()["aptitude_taken"] is True


def test_the_quiz_asks_topics_in_the_banks_order(client, content, bank, newcomer):
    """The order comes from content.aptitude_bank.changed as given; a reorder re-sends it."""
    festivals = next(topic for topic in content.topics if topic.name == "Festivals")
    content.update_topic(festivals, position=-1)

    assert client.post("/api/aptitude/start").json()["question"]["topic"] == "Festivals"


def test_leaving_an_incomplete_quiz_saves_no_attempt_or_exemption(client, db, bank, newcomer):
    question = client.post("/api/aptitude/start").json()["question"]
    model = db.get(QuizQuestion, question["id"])
    client.post(
        "/api/aptitude/next",
        json={"answers": [{"question_id": question["id"], "option_id": model.correct_option_id}]},
    )

    assert db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == newcomer.id)) is None
    assert (
        list(db.scalars(select(TopicExemption).where(TopicExemption.user_id == newcomer.id))) == []
    )
    restarted = client.post("/api/aptitude/start").json()["question"]
    assert restarted["level"] == 1


def test_inactive_question_is_not_selected_for_a_new_quiz(client, content, bank, newcomer):
    first_topic = content.topics[0]
    original = bank[first_topic, 1]
    replacement = content.question(
        first_topic,
        1,
        prompt="Replacement",
        options=[{"id": "yes", "text": "Yes"}, {"id": "no", "text": "No"}],
        correct="yes",
    )
    content.update_question(original, is_active=False)

    selected = client.post("/api/aptitude/start").json()["question"]
    assert selected["id"] == str(replacement.id)


def test_a_stale_question_event_does_not_undo_a_newer_one(client, bus, content, bank, newcomer):
    """Out of order: the deactivation (v2) arrives, then the original (v1) again."""
    first_topic = content.topics[0]
    original = bank[first_topic, 1]
    replacement = content.question(first_topic, 1, prompt="Replacement")
    stale = next(
        e
        for e in bus.sent
        if e["type"] == "content.aptitude_question.changed"
        and e["aggregate_id"] == str(original.id)
    )
    content.update_question(original, is_active=False)
    bus.deliver(stale)

    selected = client.post("/api/aptitude/start").json()["question"]
    assert selected["id"] == str(replacement.id)


def test_singaporean_cannot_take_the_newcomer_quiz(client, bank, make_user):
    sign_in(client, make_user("local@example.com", user_type="singaporean"))

    response = client.post("/api/aptitude/start")
    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "quiz_for_newcomers",
        "message": "The aptitude test is for Newcomers.",
    }


def test_a_newcomer_without_a_profile_can_take_the_quiz(client, bank, make_user):
    """SCRUM-98: profile setup can be skipped (SCRUM-14), so the quiz no longer needs one."""
    sign_in(client, make_user("new@example.com", profile_completed=False))

    assert client.post("/api/aptitude/start").status_code == 200


def test_there_is_no_skip_endpoint(client, db, bank, newcomer):
    """ "Skip for now" only leaves the page; nothing is stored, so there is nothing to call."""
    assert client.post("/api/aptitude/skip").status_code == 404
    assert db.scalar(select(AptitudeAttempt)) is None


def test_quiz_options_are_shuffled_and_end_with_not_sure(client, db, bank, newcomer):
    question = client.post("/api/aptitude/start").json()["question"]
    model = db.get(QuizQuestion, question["id"])

    assert question["options"][-1] == NOT_SURE_OPTION
    assert sorted(option["id"] for option in question["options"][:-1]) == sorted(
        option["id"] for option in model.options
    )

    model.options = [{"id": c, "text": c.upper()} for c in "abcd"]
    orders = {tuple(option["id"] for option in _quiz_options(model)[:-1]) for _ in range(50)}
    assert len(orders) > 1


def test_not_sure_counts_as_wrong(client, db, bank, newcomer):
    current = client.post("/api/aptitude/start").json()["question"]
    first_topic = current["topic_id"]
    answers = [{"question_id": current["id"], "option_id": NOT_SURE_OPTION["id"]}]

    step = client.post("/api/aptitude/next", json={"answers": answers}).json()
    assert step["question"]["topic_id"] != first_topic
    assert step["question"]["level"] == 1

    current = step["question"]
    while current is not None:
        answers.append({"question_id": current["id"], "option_id": NOT_SURE_OPTION["id"]})
        current = client.post("/api/aptitude/next", json={"answers": answers}).json()["question"]
    result = client.post("/api/aptitude/submit", json={"answers": answers}).json()
    assert result["correct"] == 0
    assert all(placement["level"] == 0 for placement in result["placements"])
    attempt = db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == newcomer.id))
    assert attempt.results[0]["option_text"] == NOT_SURE_OPTION["text"]
    assert attempt.results[0]["correct"] is False


def test_answers_off_the_quiz_path_are_refused(client, db, content, bank, newcomer):
    level_two = bank[content.topics[0], 2]
    response = client.post(
        "/api/aptitude/next",
        json={"answers": [{"question_id": str(level_two.id), "option_id": "a"}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "invalid_quiz_path",
        "message": "The answers do not follow the aptitude test's order.",
    }


def test_an_unfinished_quiz_cannot_be_submitted(client, db, bank, newcomer):
    question = client.post("/api/aptitude/start").json()["question"]
    response = client.post(
        "/api/aptitude/submit",
        json={"answers": [{"question_id": question["id"], "option_id": "not-sure"}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "quiz_incomplete"


def test_a_bank_that_is_not_ready_refuses_with_its_topics(client, content, newcomer):
    """Readiness is Content's (aptitude_bank.changed); the message names the topics it says
    are not ready, as before the split."""
    singlish, hawker = content.topic("Singlish", 0), content.topic("Hawker & Food", 1)
    content.full_bank([singlish])
    content.question(hawker, 1)

    response = client.post("/api/aptitude/start")
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "aptitude_not_ready",
        "message": "The aptitude test is not ready. Add active questions at every level for "
        "Hawker & Food.",
    }


def test_an_empty_bank_is_not_ready_for_all_topics(client, newcomer):
    response = client.post("/api/aptitude/start")
    assert response.status_code == 409
    assert response.json()["detail"]["message"] == (
        "The aptitude test is not ready. Add active questions at every level for all topics."
    )


def test_a_stale_bank_event_is_ignored(client, bus, content, newcomer):
    """The bank's revision orders its events: an older, not-ready bank arriving late does
    not undo a newer, ready one."""
    topic = content.topic("Singlish")
    content.full_bank([topic])
    not_ready = [e for e in bus.sent if e["type"] == "content.aptitude_bank.changed"][0]
    bus.deliver(not_ready)

    assert client.post("/api/aptitude/start").status_code == 200
