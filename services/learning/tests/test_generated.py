"""AI-generated lessons (docs/ai-lessons-plan.md, docs/ai-lessons-api.md "Learning"): options,
the request and its event, the daily limit, Generation's answers, cancel and timeout, playing,
rating, reports and erasure. Generation is played by envelopes checked against contracts/."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.models import (
    GeneratedLesson,
    GeneratedLessonAnswer,
    GeneratedLessonAttempt,
    GeneratedLessonReport,
    LessonAttempt,
    LessonCompletion,
    outbox,
)
from app.platform.outbox import envelope as outbox_envelope
from tests.conftest import sign_in
from tests.support.events import validate
from tests.support.records import complete, quiz

DOC = {
    "cards": [
        {"id": "intro", "text": "Short answers do a lot of work."},
        {
            "id": "c1",
            "text": "Lunch at 12, can or not? You reply {{blank}}.",
            "question": {
                "id": "q1",
                "options": [
                    {"id": "can", "text": "Can!", "correct": True},
                    {"id": "stiff", "text": "Yes, that works.", "why_not": "Sounds stiff."},
                ],
                "explanation": "A quick question gets a quick answer.",
            },
        },
    ]
}

LESSON_DATA = {
    "title": "Can or Not? Lunch with Colleagues",
    "summary": 'Answer "can or not?" the local way.',
    "learning_points": ["Reply with one word", "Sound friendly"],
    "doc": {
        "cards": [
            {
                "type": "story",
                "id": "c1",
                "text": "At work, *can or not?* is a quick question.",
                "image": None,
                "audio": None,
                "question": None,
            },
            {
                "type": "story",
                "id": "c2",
                "text": "The natural reply is {{blank}}.",
                "image": None,
                "audio": None,
                "question": {
                    "type": "choice",
                    "id": "q1",
                    "explanation": "A quick question gets a quick answer.",
                    "shuffle": True,
                    "options": [
                        {"id": "o1", "text": "Can!", "correct": True, "why_not": ""},
                        {"id": "o2", "text": "Yes.", "correct": False, "why_not": "Stiff."},
                    ],
                },
            },
            {
                "type": "story",
                "id": "c3",
                "text": "Not okay is {{blank}}.",
                "image": None,
                "audio": None,
                "question": {
                    "type": "choice",
                    "id": "q2",
                    "explanation": "Cannot is the short no.",
                    "shuffle": False,
                    "options": [
                        {"id": "o1", "text": "Cannot", "correct": True, "why_not": ""},
                        {"id": "o2", "text": "No can", "correct": False, "why_not": "Not used."},
                    ],
                },
            },
        ]
    },
    "questions": [
        {"card_id": "c2", "question_id": "q1", "scored": True, "correct_option_id": "o1"},
        {"card_id": "c3", "question_id": "q2", "scored": True, "correct_option_id": "o1"},
    ],
    "reading_seconds": 60,
    "cards_plain_text": ["At work, can or not? is a quick question.", "Reply ___.", "No ___."],
}

BODY = {"topic_id": None, "focus": "new", "ask": None, "difficulty": "right", "length": "usual"}


# --- Helpers --------------------------------------------------------------------------------


def _generation(bus, type: str, request_id, version: int, requester="learning", **data):
    """Deliver a Generation event for a request, checked against its contract."""
    envelope = bus.envelope(
        f"generation.lesson.{type}",
        {"request_id": str(request_id), "requester": requester, **data},
        request_id,
        version,
        aggregate_type="lesson_generation",
    )
    bus.deliver(envelope)
    return envelope


def progress(bus, request_id, stage: str, **kwargs):
    version = {"writing": 1, "checking": 2}[stage]
    return _generation(bus, "progress", request_id, version, stage=stage, **kwargs)


def generated(bus, request_id, **kwargs):
    return _generation(bus, "generated", request_id, 3, **LESSON_DATA, **kwargs)


def failed(bus, request_id, code="invalid_output"):
    return _generation(bus, "failed", request_id, 3, code=code, detail="for logs")


def generate(client, expect=202, **changes) -> dict:
    response = client.post("/api/generate", json={**BODY, **changes})
    assert response.status_code == expect, response.text
    return response.json()


def run_lesson(client, lesson, option: str) -> None:
    """Take a published lesson once, answering q1 with `option` (a mistake if "stiff")."""
    attempt = client.post(
        f"/api/lessons/{lesson.id}/attempts", json={"version": len(lesson.versions)}
    ).json()["id"]
    client.post(f"/api/attempts/{attempt}/answers", json={"question_id": "q1", "option_id": option})
    assert client.post(f"/api/attempts/{attempt}/finish").status_code == 200


def events(db) -> list[dict]:
    return [outbox_envelope(row) for row in db.execute(select(outbox).order_by(outbox.c.id))]


def row_of(db, generated_id) -> GeneratedLesson:
    db.expire_all()
    return db.get(GeneratedLesson, uuid.UUID(str(generated_id)))


def count(db, model, *where) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model).where(*where))


@pytest.fixture
def world(content):
    singlish = content.topic("Singlish", 0, description="Little words you hear every day.")
    food = content.topic("Hawker & Food", 1)
    lessons = {
        "lah": content.lesson(singlish, "Lah", level=1, position=0, doc=DOC, summary="Particles"),
        "can": content.lesson(singlish, "Could, Can and One", level=2, position=1, doc=DOC),
        "advanced": content.lesson(singlish, "Advanced", level=4, position=2, doc=DOC),
        "kopi": content.lesson(food, "Kopi", level=1, doc=DOC),
    }
    return singlish, food, lessons


@pytest.fixture
def maria(client, make_user):
    user = make_user("maria@example.com")
    sign_in(client, user)
    return user


def ready_lesson(client, bus, **changes) -> str:
    status = generate(client, **changes)
    generated(bus, status["id"])
    return status["id"]


# --- Options --------------------------------------------------------------------------------


def test_generating_needs_a_signed_in_learner(client):
    assert client.get("/api/generate/options").status_code == 401
    assert client.post("/api/generate", json=BODY).status_code == 401


def test_options_for_a_new_learner(client, world, maria):
    singlish, food, _ = world
    options = client.get("/api/generate/options").json()
    assert options == {
        "daily_limit": 3,
        "left_today": 3,
        "has_generated": False,
        "mistakes_total": 0,
        "pick_for_me": {"new": str(singlish.id), "mistakes": None},
        "topics": [
            {"id": str(singlish.id), "name": "Singlish", "mistakes": 0, "level": 1},
            {"id": str(food.id), "name": "Hawker & Food", "mistakes": 0, "level": 1},
        ],
    }


def test_options_count_mistakes_per_topic_and_pick_the_topic_with_most(client, world, maria):
    singlish, food, lessons = world
    run_lesson(client, lessons["lah"], "stiff")
    run_lesson(client, lessons["can"], "stiff")
    run_lesson(client, lessons["kopi"], "stiff")
    options = client.get("/api/generate/options").json()
    assert options["mistakes_total"] == 3
    assert [t["mistakes"] for t in options["topics"]] == [2, 1]
    assert options["pick_for_me"]["mistakes"] == str(singlish.id)
    # Something new: Singlish has 2 of 3 done, food 1 of 1, so Singlish is the weakest.
    assert options["pick_for_me"]["new"] == str(singlish.id)
    # The mistakes are exactly Review's.
    assert len(client.get("/api/review").json()["mistakes"]) == 3


def test_a_tie_on_mistakes_goes_to_the_most_recent(client, world, maria):
    _, food, lessons = world
    run_lesson(client, lessons["lah"], "stiff")
    run_lesson(client, lessons["kopi"], "stiff")
    assert client.get("/api/generate/options").json()["pick_for_me"]["mistakes"] == str(food.id)


def test_level_is_the_exemption_else_the_highest_completed_else_1(client, db, world, maria):
    singlish, food, lessons = world
    complete(db, maria, lessons["can"])  # level 2 in Singlish
    quiz(db, maria, {food: 3, singlish: 0})  # 0 exempts nothing, so completion decides
    levels = [t["level"] for t in client.get("/api/generate/options").json()["topics"]]
    assert levels == [2, 3]


# --- The request ----------------------------------------------------------------------------


def test_a_request_saves_the_row_and_its_event_together(client, db, world, maria):
    singlish, _, lessons = world
    run_lesson(client, lessons["lah"], "stiff")
    status = generate(
        client,
        topic_id=str(singlish.id),
        focus="mistakes",
        ask="  My colleagues keep asking can or not  ",
        difficulty="harder",
    )
    assert status["status"] == "requested"
    assert status["topic"] == {"id": str(singlish.id), "name": "Singlish"}
    assert status["level"] == 2  # level 1 + harder
    assert status["ask"] == "My colleagues keep asking can or not"
    assert status["covers"] == [
        {"lesson_id": str(lessons["lah"].id), "lesson_title": "Lah", "correct": "Can!"}
    ]
    assert status["lesson"] is None and status["failure"] is None
    assert status["left_today"] == 2

    [event] = events(db)
    validate(event)
    assert event["type"] == "learning.lesson_generation.requested"
    assert event["producer"] == "learning"
    assert event["aggregate_id"] == status["id"] and event["aggregate_version"] == 1
    data = event["data"]
    assert data["request_id"] == status["id"]
    assert data["brief"] == {
        "audience": "learner",
        "focus": "mistakes",
        "topic": {
            "id": str(singlish.id),
            "name": "Singlish",
            "description": "Little words you hear every day.",
        },
        "level": 2,
        "cards": 6,
        "questions": 2,
        "ask": "My colleagues keep asking can or not",
        "notes": None,
        "check_answers": True,
    }
    grounding = data["grounding"]
    # Nearest the level (2) first: 2, then 1, then 4.
    assert [lesson["title"] for lesson in grounding["lessons"]] == [
        "Could, Can and One",
        "Lah",
        "Advanced",
    ]
    assert grounding["lessons"][1]["summary"] == "Particles"
    assert grounding["mistakes"] == [
        {
            "lesson_title": "Lah",
            "card_text": "Lunch at 12, can or not? You reply {{blank}}.",
            "chosen": "Yes, that works.",
            "correct": "Can!",
            "explanation": "A quick question gets a quick answer.",
            "why_not": "Sounds stiff.",
        }
    ]
    assert grounding["avoid_titles"] == [] and grounding["feedback"] == []
    # Nothing personal leaves Learning.
    assert str(maria.id) not in json.dumps(event)
    assert "maria" not in json.dumps(event)


def test_pick_for_me_and_short_and_empty_ask(client, db, world, maria):
    singlish, _, _ = world
    status = generate(client, ask="   ", length="short", difficulty="easier")
    assert status["topic"]["id"] == str(singlish.id)
    assert status["ask"] is None
    assert status["level"] == 1  # never below 1
    brief = events(db)[0]["data"]["brief"]
    assert (brief["cards"], brief["questions"], brief["ask"]) == (4, 1, None)
    assert events(db)[0]["data"]["grounding"]["mistakes"] == []


def test_ask_over_200_characters_is_refused(client, world, maria):
    generate(client, expect=422, ask="x" * 201)


def test_no_mistakes_and_unknown_topics(client, content, world, maria):
    singlish, _, _ = world
    assert generate(client, expect=409, focus="mistakes")["detail"]["code"] == "no_mistakes"
    body = generate(client, expect=409, focus="mistakes", topic_id=str(singlish.id))
    assert body["detail"]["code"] == "no_mistakes"
    body = generate(client, expect=404, topic_id=str(uuid.uuid4()))
    assert body["detail"]["code"] == "topic_not_found"
    empty = content.topic("Empty")
    content.lesson(empty, "Gone", status="withdrawn")
    body = generate(client, expect=404, topic_id=str(empty.id))
    assert body["detail"]["code"] == "topic_not_found"
    assert client.get("/api/generate/options").json()["left_today"] == 3


def test_the_daily_limit_and_refunds(client, bus, world, maria):
    first = generate(client)
    second = generate(client)
    third = generate(client)
    assert third["left_today"] == 0
    body = generate(client, expect=429)
    assert body["detail"] == {
        "code": "daily_limit_reached",
        "message": "You have reached today's limit of 3 generated lessons. "
        "You can generate more tomorrow.",
        "left_today": 0,
    }
    # A failure and a cancel each give the slot back.
    failed(bus, first["id"])
    assert client.get("/api/generate/options").json()["left_today"] == 1
    client.post(f"/api/generate/{second['id']}/cancel")
    assert generate(client)["left_today"] == 1


def test_yesterdays_requests_do_not_count(client, db, world, maria):
    for _ in range(3):
        generate(client)
    db.execute(
        update(GeneratedLesson).values(
            created_at=datetime.now(UTC) - timedelta(days=1), status="ready"
        )
    )
    db.commit()
    assert generate(client)["left_today"] == 2


def test_later_requests_avoid_earlier_titles_and_carry_feedback(client, db, bus, world, maria):
    singlish, _, _ = world
    first = ready_lesson(client, bus, topic_id=str(singlish.id))
    client.post(f"/api/generated/{first}/rating", json={"useful": False, "reasons": ["too_easy"]})
    generate(client, topic_id=str(singlish.id))
    event = events(db)[-1]
    validate(event)
    assert event["data"]["grounding"]["avoid_titles"] == [LESSON_DATA["title"]]
    assert event["data"]["grounding"]["feedback"] == [
        {"title": LESSON_DATA["title"], "useful": False, "reasons": ["too_easy"]}
    ]


# --- Generation's answers -------------------------------------------------------------------


def test_progress_then_the_lesson(client, bus, world, maria):
    request_id = generate(client)["id"]
    progress(bus, request_id, "writing")
    assert client.get(f"/api/generate/{request_id}").json()["status"] == "writing"
    progress(bus, request_id, "checking")
    assert client.get(f"/api/generate/{request_id}").json()["status"] == "checking"
    generated(bus, request_id)
    status = client.get(f"/api/generate/{request_id}").json()
    assert status["status"] == "ready"
    assert status["lesson"] == {
        "title": LESSON_DATA["title"],
        "summary": LESSON_DATA["summary"],
        "learning_points": LESSON_DATA["learning_points"],
        "cards": 3,
        "questions": 2,
        "reading_seconds": 60,
    }


def test_events_out_of_order_and_twice_change_nothing(client, db, bus, world, maria):
    request_id = generate(client)["id"]
    progress(bus, request_id, "checking")
    progress(bus, request_id, "writing")  # older: ignored
    assert row_of(db, request_id).status == "checking"
    generated(bus, request_id)
    generated(bus, request_id)  # duplicate
    failed(bus, request_id)  # a result after the result
    progress(bus, request_id, "writing")
    row = row_of(db, request_id)
    assert (row.status, row.version, row.title) == ("ready", 3, LESSON_DATA["title"])


def test_a_result_before_any_progress_is_kept(client, db, bus, world, maria):
    request_id = generate(client)["id"]
    generated(bus, request_id)
    progress(bus, request_id, "checking")
    assert row_of(db, request_id).status == "ready"


def test_other_requesters_and_unknown_requests_are_ignored(client, db, bus, world, maria):
    request_id = generate(client)["id"]
    generated(bus, request_id, requester="content")
    assert row_of(db, request_id).status == "requested"
    generated(bus, uuid.uuid4())  # acknowledged, nothing to do


def test_failures_say_why_in_plain_words(client, bus, world, maria):
    off_topic, unsafe = generate(client)["id"], generate(client)["id"]
    failed(bus, off_topic, "off_topic")
    failed(bus, unsafe, "unsafe")
    status = client.get(f"/api/generate/{off_topic}").json()
    assert status["status"] == "failed"
    assert status["failure"] == {
        "code": "off_topic",
        "message": "We couldn't create a lesson from that request. Lessons cover everyday "
        "life in Singapore, such as small talk at work or ordering food. Please rephrase it "
        "and try again.",
    }
    assert (
        client.get(f"/api/generate/{unsafe}")
        .json()["failure"]["message"]
        .startswith("This lesson did not pass our quality checks")
    )
    assert status["left_today"] == 3


def test_cancel_then_a_late_result_is_ignored(client, db, bus, world, maria):
    request_id = generate(client)["id"]
    progress(bus, request_id, "writing")
    status = client.post(f"/api/generate/{request_id}/cancel").json()
    assert status["status"] == "cancelled" and status["left_today"] == 3
    generated(bus, request_id)
    assert row_of(db, request_id).status == "cancelled"
    assert client.get("/api/generated").json() == []


def test_cancelling_a_finished_request_changes_nothing(client, bus, world, maria):
    request_id = ready_lesson(client, bus)
    assert client.post(f"/api/generate/{request_id}/cancel").json()["status"] == "ready"


def test_a_request_waiting_too_long_times_out_when_read(client, db, bus, world, maria):
    request_id = generate(client)["id"]
    progress(bus, request_id, "writing")
    db.execute(update(GeneratedLesson).values(created_at=datetime.now(UTC) - timedelta(seconds=91)))
    db.commit()
    status = client.get(f"/api/generate/{request_id}").json()
    assert status["status"] == "failed"
    assert status["failure"] == {
        "code": "timeout",
        "message": "We couldn't create this lesson right now. Please try again shortly.",
    }
    assert status["left_today"] == 3
    row = row_of(db, request_id)
    assert row.failure_code == "timeout" and row.failed_at is not None
    generated(bus, request_id)  # too late
    assert row_of(db, request_id).status == "failed"


def test_a_result_arriving_after_the_timeout_is_ignored_even_unread(client, db, bus, world, maria):
    request_id = generate(client)["id"]
    db.execute(update(GeneratedLesson).values(created_at=datetime.now(UTC) - timedelta(seconds=91)))
    db.commit()
    generated(bus, request_id)
    row = row_of(db, request_id)
    assert (row.status, row.failure_code) == ("failed", "timeout")


def test_the_list_newest_first_without_failed_or_cancelled(client, bus, world, maria):
    ready = ready_lesson(client, bus)
    gone = generate(client)["id"]
    failed(bus, gone)
    waiting = generate(client)["id"]
    listed = client.get("/api/generated").json()
    assert [(item["id"], item["status"]) for item in listed] == [
        (waiting, "requested"),
        (ready, "ready"),
    ]
    assert listed[1]["title"] == LESSON_DATA["title"]
    assert listed[1]["best"] is None
    assert listed[1]["topic"]["name"] == "Singlish"


def test_other_users_get_404(client, bus, world, maria, make_user):
    request_id = ready_lesson(client, bus)
    attempt = client.post(f"/api/generated/{request_id}/attempts").json()["id"]
    sign_in(client, make_user("other@example.com"))
    for path in (f"/api/generate/{request_id}", f"/api/generated/{request_id}/lesson"):
        assert client.get(path).json()["detail"]["code"] == "generated_not_found"
    for path in (
        f"/api/generate/{request_id}/cancel",
        f"/api/generated/{request_id}/attempts",
    ):
        assert client.post(path).status_code == 404
    assert (
        client.post(f"/api/generated/{request_id}/rating", json={"useful": True}).status_code == 404
    )
    response = client.post(
        f"/api/generated/attempts/{attempt}/answers", json={"question_id": "q1", "option_id": "o1"}
    )
    assert response.json()["detail"]["code"] == "attempt_not_found"
    assert client.post(f"/api/generated/attempts/{attempt}/finish").status_code == 404
    assert client.get("/api/generated").json() == []


# --- Playing --------------------------------------------------------------------------------


def test_only_a_ready_lesson_can_be_opened(client, world, maria):
    request_id = generate(client)["id"]
    response = client.get(f"/api/generated/{request_id}/lesson")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "generated_not_found"
    assert client.post(f"/api/generated/{request_id}/attempts").status_code == 404


def test_the_lesson_is_a_learner_deck_without_answers(client, bus, world, maria):
    singlish, _, _ = world
    request_id = ready_lesson(client, bus)
    lesson = client.get(f"/api/generated/{request_id}/lesson").json()
    assert lesson["id"] == request_id
    assert lesson["version"] == 1
    assert lesson["title"] == LESSON_DATA["title"]
    assert lesson["topic"] == {"id": str(singlish.id), "name": "Singlish"}
    assert lesson["reading_seconds"] == 60
    assert lesson["assets"] == {}
    assert [card["id"] for card in lesson["cards"]] == ["c1", "c2", "c3"]
    question = lesson["cards"][1]["question"]
    assert question["scored"] is True
    assert {option["id"] for option in question["options"]} == {"o1", "o2"}
    assert "correct" not in json.dumps(lesson)
    assert "why_not" not in json.dumps(lesson)
    # Not shuffled where the lesson says so.
    assert [o["id"] for o in lesson["cards"][2]["question"]["options"]] == ["o1", "o2"]


def test_attempts_answers_and_finish(client, db, bus, world, maria):
    request_id = ready_lesson(client, bus)
    start = client.post(f"/api/generated/{request_id}/attempts")
    assert start.status_code == 201
    attempt = start.json()["id"]

    def answer(question_id, option_id, attempt_id=attempt):
        return client.post(
            f"/api/generated/attempts/{attempt_id}/answers",
            json={"question_id": question_id, "option_id": option_id},
        )

    wrong = answer("q1", "o2")
    assert wrong.json() == {
        "correct": False,
        "correct_option_id": "o1",
        "why_not": "Stiff.",
        "explanation": "A quick question gets a quick answer.",
    }
    # Only the first answer counts.
    assert answer("q1", "o1").json()["correct"] is False
    assert answer("nope", "o1").json()["detail"]["code"] == "question_not_found"
    assert answer("q2", "zz").json()["detail"]["code"] == "option_not_found"

    unfinished = client.post(f"/api/generated/attempts/{attempt}/finish")
    assert unfinished.status_code == 409
    assert unfinished.json()["detail"]["question_ids"] == ["q2"]

    assert answer("q2", "o1").json()["correct"] is True
    finished = client.post(f"/api/generated/attempts/{attempt}/finish").json()
    assert finished == {
        "attempt_id": attempt,
        "score": {"correct": 1, "scored": 2},
        "best": {"correct": 1, "scored": 2},
    }
    # Finishing again changes nothing; answering a finished attempt is refused.
    assert client.post(f"/api/generated/attempts/{attempt}/finish").json() == finished
    assert answer("q1", "o1").status_code == 409

    # A better retake becomes the best; a worse one never lowers it.
    for options in ({"q1": "o1", "q2": "o1"}, {"q1": "o2", "q2": "o2"}):
        retake = client.post(f"/api/generated/{request_id}/attempts").json()["id"]
        for question_id, option_id in options.items():
            answer(question_id, option_id, retake)
        result = client.post(f"/api/generated/attempts/{retake}/finish").json()
        assert result["best"] == {"correct": 2, "scored": 2}
    assert client.get("/api/generated").json()[0]["best"] == {"correct": 2, "scored": 2}
    assert count(db, GeneratedLessonAttempt) == 3
    assert count(db, GeneratedLessonAnswer) == 6


def test_playing_never_touches_progress_or_review(client, db, bus, world, maria):
    _, _, lessons = world
    run_lesson(client, lessons["lah"], "stiff")
    before = (client.get("/api/progress").json(), client.get("/api/review").json())
    attempts_before = count(db, LessonAttempt)
    completions_before = count(db, LessonCompletion)

    request_id = ready_lesson(client, bus, focus="mistakes")
    attempt = client.post(f"/api/generated/{request_id}/attempts").json()["id"]
    for question_id in ("q1", "q2"):
        client.post(
            f"/api/generated/attempts/{attempt}/answers",
            json={"question_id": question_id, "option_id": "o1"},
        )
    assert client.post(f"/api/generated/attempts/{attempt}/finish").status_code == 200

    assert (client.get("/api/progress").json(), client.get("/api/review").json()) == before
    assert count(db, LessonAttempt) == attempts_before
    assert count(db, LessonCompletion) == completions_before


# --- Rating and reports ---------------------------------------------------------------------


def test_rating_saves_and_replaces(client, db, bus, world, maria):
    request_id = ready_lesson(client, bus)
    path = f"/api/generated/{request_id}/rating"
    response = client.post(path, json={"useful": False, "reasons": ["too_easy", "not_relevant"]})
    assert response.status_code == 204
    assert client.post(path, json={"useful": True, "reasons": ["clear"]}).status_code == 204
    row = row_of(db, request_id)
    assert (row.rating_useful, row.rating_reasons) == (True, ["clear"])
    too_many = ["clear", "too_easy", "too_hard", "not_relevant", "right_level"]
    assert client.post(path, json={"useful": True, "reasons": too_many}).status_code == 422
    assert client.post(path, json={"useful": True, "reasons": ["nice"]}).status_code == 422


def test_reports_are_stored_here(client, db, bus, world, maria):
    request_id = ready_lesson(client, bus)
    path = f"/api/generated/{request_id}/reports"
    response = client.post(path, json={"card_id": "c2", "reason": "wrong", "note": "  Hmm  "})
    assert response.status_code == 201
    assert set(response.json()) == {"id", "created_at"}
    [report] = db.scalars(select(GeneratedLessonReport)).all()
    assert (report.card_id, report.reason, report.note) == ("c2", "wrong", "Hmm")
    bad_card = client.post(path, json={"card_id": "zz", "reason": "typo"})
    assert bad_card.json()["detail"]["code"] == "card_not_found"
    assert client.post(path, json={"card_id": "c1", "reason": "boring"}).status_code == 422
    assert (
        client.post(path, json={"card_id": "c1", "reason": "other", "note": "x" * 501}).status_code
        == 422
    )


# --- Erasure --------------------------------------------------------------------------------


def test_deleting_an_account_erases_its_generated_lessons(
    client, db, bus, identity, world, maria, make_user
):
    request_id = ready_lesson(client, bus)
    attempt = client.post(f"/api/generated/{request_id}/attempts").json()["id"]
    client.post(
        f"/api/generated/attempts/{attempt}/answers",
        json={"question_id": "q1", "option_id": "o1"},
    )
    client.post(f"/api/generated/{request_id}/reports", json={"card_id": "c1", "reason": "typo"})
    generate(client)  # still waiting
    other = make_user("other@example.com")
    sign_in(client, other)
    kept = ready_lesson(client, bus)

    identity.delete(maria)

    assert count(db, GeneratedLesson, GeneratedLesson.user_id == maria.id) == 0
    assert count(db, GeneratedLesson) == 1
    assert row_of(db, kept) is not None
    assert count(db, GeneratedLessonAttempt) == 0
    assert count(db, GeneratedLessonAnswer) == 0
    assert count(db, GeneratedLessonReport) == 0
