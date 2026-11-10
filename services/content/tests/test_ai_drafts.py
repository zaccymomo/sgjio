"""AI-drafted lessons for administrators (app/generation.py, docs/ai-lessons-api.md "Content"):
the request and its event, the daily limit, Generation's answers becoming a Draft, the review
tick on first publish, and erasure.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app import lesson_doc
from app.consumers import build_consumer
from app.lesson_doc import LessonDoc
from app.models import GenerationJob, GenerationStatus, Lesson, LessonOrigin
from app.platform.consumer import Outcome
from app.platform.testing import make_envelope
from tests.conftest import ADMIN_ID, contract_problems, outbox_events

TOPICS = "/api/admin/topics"
LESSONS = "/api/admin/lessons"
GENERATE = "/api/admin/lessons/generate"

READY_DOC = {
    "cards": [
        {"text": "**Kopi** is coffee with _condensed_ milk."},
        {
            "text": "Black coffee with sugar is kopi {{blank}}.",
            "question": {
                "options": [
                    {"text": "O", "correct": True},
                    {"text": "C", "why_not": "Milk."},
                ],
                "explanation": "O means no milk.",
            },
        },
    ]
}

# A generated deck, as generation.lesson.generated carries it (the published-version shape).
GENERATED_DOC = {
    "cards": [
        {
            "type": "story",
            "id": "c1",
            "text": "At work, *can or not?* is a quick yes-or-no question.",
            "image": None,
            "audio": None,
            "question": None,
        },
        {
            "type": "story",
            "id": "c2",
            "text": 'Your colleague asks, "Lunch at 12, can or not?" The reply is {{blank}}.',
            "image": None,
            "audio": None,
            "question": {
                "type": "choice",
                "id": "q1",
                "explanation": "A quick question gets a quick answer.",
                "shuffle": True,
                "options": [
                    {"id": "o1", "text": "Can!", "correct": True, "why_not": ""},
                    {
                        "id": "o2",
                        "text": "Yes, that timing works well for me.",
                        "correct": False,
                        "why_not": "Polite, but stiff here.",
                    },
                ],
            },
        },
    ]
}


def _topic(admin, name="Workplace", description="Getting along at work.") -> dict:
    response = admin.post(TOPICS, json={"name": name, "description": description})
    assert response.status_code == 201, response.json()
    return response.json()


def _published(admin, topic: dict, title: str, level: int = 1) -> dict:
    body = {"title": title, "summary": "S", "topic_id": topic["id"], "doc": READY_DOC}
    lesson = admin.post(LESSONS, json={**body, "level": level}).json()
    response = admin.post(
        f"{LESSONS}/{lesson['id']}/publish", json={"updated_at": lesson["updated_at"]}
    )
    assert response.status_code == 200, response.json()
    return response.json()


def _generate(admin, topic: dict, **fields):
    body = {"topic_id": topic["id"], "level": 2, "notes": "Saying no indirectly.", "cards": 6}
    return admin.post(GENERATE, json={**body, **fields})


def _job(admin, topic: dict) -> dict:
    response = _generate(admin, topic)
    assert response.status_code == 202, response.json()
    return response.json()


def _answer(type_: str, job_id: str, version: int, requester="content", **data) -> bytes:
    body = {"request_id": job_id, "requester": requester, **data}
    envelope = make_envelope(type_, body, job_id, version, aggregate_type="lesson_generation")
    return json.dumps(envelope).encode()


def _generated(job_id: str, requester="content", title="Can or Not? Lunch with Colleagues"):
    return _answer(
        "generation.lesson.generated",
        job_id,
        3,
        requester,
        title=title,
        summary='Answer "can or not?" the local way.',
        learning_points=["Reply with one word"],
        doc=GENERATED_DOC,
        questions=[
            {"card_id": "c2", "question_id": "q1", "scored": True, "correct_option_id": "o1"}
        ],
        reading_seconds=40,
        cards_plain_text=["At work, can or not?", "The reply is ___."],
    )


def _failed(job_id: str, code="off_topic") -> bytes:
    return _answer("generation.lesson.failed", job_id, 3, code=code, detail="refused")


def _progress(job_id: str, version=1, stage="writing") -> bytes:
    return _answer("generation.lesson.progress", job_id, version, stage=stage)


def _status(admin, job_id: str) -> dict:
    response = admin.get(f"/api/admin/generation/{job_id}")
    assert response.status_code == 200, response.json()
    return response.json()


# --- The request ----------------------------------------------------------------------------


def test_a_request_saves_the_job_and_sends_the_brief_and_grounding(admin, db, contract_validators):
    topic = _topic(admin)
    _published(admin, topic, "Could, Can and One", level=1)
    _published(admin, topic, "Saying Lah", level=3)
    admin.post(LESSONS, json={"title": "Unpublished idea", "topic_id": topic["id"], "level": 2})
    other = _topic(admin, "Food")
    _published(admin, other, "Ordering kopi")

    response = _generate(admin, topic, notes="  Saying no to a manager: can try, but...  ")

    assert response.status_code == 202, response.json()
    job = response.json()
    assert job["status"] == "requested"
    assert job["lesson_id"] is None and job["failure"] is None
    assert job["left_today"] == 19
    row = db.get(GenerationJob, uuid.UUID(job["id"]))
    assert (row.requested_by, row.level, row.cards, row.notes) == (
        ADMIN_ID,
        2,
        6,
        "Saying no to a manager: can try, but...",
    )
    [event] = outbox_events("content.lesson_generation.requested")
    assert contract_problems(contract_validators, event) == []
    assert (event["aggregate_id"], event["aggregate_version"]) == (job["id"], 1)
    assert event["data"]["brief"] == {
        "audience": "admin",
        "focus": "notes",
        "topic": {"id": topic["id"], "name": "Workplace", "description": "Getting along at work."},
        "level": 2,
        "cards": 6,
        "questions": 2,
        "ask": None,
        "notes": "Saying no to a manager: can try, but...",
        "check_answers": False,
    }
    grounding = event["data"]["grounding"]
    assert [lesson["title"] for lesson in grounding["lessons"]] == [
        "Could, Can and One",
        "Saying Lah",
    ]
    assert grounding["lessons"][0]["cards_text"] == [
        "Kopi is coffee with condensed milk.",
        "Black coffee with sugar is kopi ___.",
    ]
    assert grounding["avoid_titles"] == ["Could, Can and One", "Unpublished idea", "Saying Lah"]
    assert grounding["mistakes"] == [] and grounding["feedback"] == []
    assert str(ADMIN_ID) not in json.dumps(event)


@pytest.mark.parametrize(("cards", "questions"), [(4, 1), (6, 2), (8, 3)])
def test_questions_follow_the_length(admin, cards, questions):
    topic = _topic(admin)
    assert _generate(admin, topic, cards=cards).status_code == 202
    [event] = outbox_events("content.lesson_generation.requested")
    assert event["data"]["brief"]["questions"] == questions


def test_a_bad_body_is_refused(admin):
    topic = _topic(admin)
    assert _generate(admin, topic, cards=5).status_code == 422
    assert _generate(admin, topic, notes="   ").status_code == 422
    assert _generate(admin, topic, notes="x" * 2001).status_code == 422
    assert _generate(admin, topic, level=6).status_code == 422


def test_an_unknown_or_archived_topic_is_not_found(admin):
    response = _generate(admin, {"id": str(uuid.uuid4())})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_not_found"
    topic = _topic(admin)
    admin.post(f"{TOPICS}/{topic['id']}/archive")
    assert _generate(admin, topic).json()["detail"]["code"] == "topic_not_found"
    assert outbox_events("content.lesson_generation.requested") == []


def test_only_administrators_can_ask(learner, client):
    body = {"topic_id": str(uuid.uuid4()), "level": 1, "notes": "x", "cards": 4}
    assert learner.post(GENERATE, json=body).status_code in (401, 403)
    assert client.post(GENERATE, json=body).status_code in (401, 403)


def test_twenty_a_day_and_failed_ones_are_refunded(admin, db):
    topic = _topic(admin)
    db.add_all(
        GenerationJob(
            requested_by=ADMIN_ID, topic_id=uuid.UUID(topic["id"]), level=1, cards=4, notes="n"
        )
        for _ in range(19)
    )
    # Someone else's and yesterday's don't count.
    db.add(
        GenerationJob(requested_by=uuid.uuid4(), topic_id=uuid.uuid4(), level=1, cards=4, notes="n")
    )
    db.add(
        GenerationJob(
            requested_by=ADMIN_ID,
            topic_id=uuid.uuid4(),
            level=1,
            cards=4,
            notes="n",
            status=GenerationStatus.DONE,
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
    )
    db.commit()
    assert admin.get("/api/admin/generation").json() == {"daily_limit": 20, "left_today": 1}
    last = _job(admin, topic)
    assert last["left_today"] == 0

    refused = _generate(admin, topic)
    assert refused.status_code == 429
    assert refused.json()["detail"] == {
        "code": "daily_limit_reached",
        "message": "You have reached today's limit of 20 AI drafts. "
        "You can generate more tomorrow.",
        "left_today": 0,
    }

    build_consumer().handle(_failed(last["id"]))
    assert _generate(admin, topic).status_code == 202


# --- Generation's answers -------------------------------------------------------------------


def test_a_generated_lesson_becomes_one_ai_draft(admin, db):
    topic = _topic(admin)
    job = _job(admin, topic)
    consumer = build_consumer()

    assert consumer.handle(_progress(job["id"])) is Outcome.ACK
    assert _status(admin, job["id"])["status"] == "writing"
    assert consumer.handle(_generated(job["id"])) is Outcome.ACK
    assert consumer.handle(_generated(job["id"])) is Outcome.ACK  # a duplicate

    assert db.scalar(select(func.count()).select_from(Lesson)) == 1
    status = _status(admin, job["id"])
    assert status["status"] == "done" and status["failure"] is None
    lesson = admin.get(f"{LESSONS}/{status['lesson_id']}").json()
    assert lesson["origin"] == "ai"
    assert lesson["ai_reviewed_at"] is None
    assert (lesson["title"], lesson["topic_id"], lesson["level"], lesson["status"]) == (
        "Can or Not? Lunch with Colleagues",
        topic["id"],
        2,
        "draft",
    )
    assert [issue for issue in lesson["issues"] if issue["severity"] == "blocker"] == []
    doc = LessonDoc.model_validate(lesson["doc"])
    ids = [card.id for card in doc.cards]
    assert "c1" not in ids and "c2" not in ids and all(ids)  # Content's own ids
    assert doc.cards[1].question.options[0].text == "Can!"
    assert [c.text for c in doc.cards] == [c["text"] for c in GENERATED_DOC["cards"]]
    assert lesson_doc.issues(doc, title=lesson["title"], has_topic=True) == []
    # A draft is never announced to Learning.
    assert outbox_events("content.lesson.") == []


def test_a_failure_is_shown_with_a_message(admin):
    topic = _topic(admin)
    job = _job(admin, topic)
    build_consumer().handle(_failed(job["id"], "provider"))
    status = _status(admin, job["id"])
    assert status["status"] == "failed"
    assert status["failure"]["code"] == "provider"
    assert status["failure"]["message"]
    assert status["left_today"] == 20


def test_events_for_others_unknown_ids_old_versions_and_finished_jobs_are_ignored(admin, db):
    topic = _topic(admin)
    job = _job(admin, topic)
    consumer = build_consumer()

    assert consumer.handle(_generated(job["id"], requester="learning")) is Outcome.ACK
    assert consumer.handle(_generated(str(uuid.uuid4()))) is Outcome.ACK
    assert _status(admin, job["id"])["status"] == "requested"

    consumer.handle(_failed(job["id"]))
    consumer.handle(_generated(job["id"]))  # after failing: ignored
    consumer.handle(_progress(job["id"]))  # older: ignored
    assert _status(admin, job["id"])["status"] == "failed"
    assert db.scalar(select(func.count()).select_from(Lesson)) == 0


def test_a_job_waiting_too_long_times_out_and_is_refunded(admin, db):
    topic = _topic(admin)
    job = _job(admin, topic)
    db.execute(
        update(GenerationJob)
        .where(GenerationJob.id == uuid.UUID(job["id"]))
        .values(created_at=datetime.now(UTC) - timedelta(seconds=91))
    )
    db.commit()
    assert admin.get("/api/admin/generation").json()["left_today"] == 20

    status = _status(admin, job["id"])
    assert status["status"] == "failed"
    assert status["failure"]["code"] == "timeout"
    db.expire_all()
    assert db.get(GenerationJob, uuid.UUID(job["id"])).finished_at is not None
    build_consumer().handle(_generated(job["id"]))  # too late
    assert db.scalar(select(func.count()).select_from(Lesson)) == 0


def test_an_unknown_job_is_not_found(admin):
    response = admin.get(f"/api/admin/generation/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "generation_not_found"


def test_a_draft_for_a_topic_archived_meanwhile_fails_instead(admin, db):
    topic = _topic(admin)
    job = _job(admin, topic)
    admin.post(f"{TOPICS}/{topic['id']}/archive")
    assert build_consumer().handle(_generated(job["id"])) is Outcome.ACK
    status = _status(admin, job["id"])
    assert status["status"] == "failed"
    assert db.scalar(select(func.count()).select_from(Lesson)) == 0


# --- Publishing needs the review tick once --------------------------------------------------


def _ai_draft(admin) -> dict:
    topic = _topic(admin)
    job = _job(admin, topic)
    build_consumer().handle(_generated(job["id"]))
    return admin.get(f"{LESSONS}/{_status(admin, job['id'])['lesson_id']}").json()


def _publish(admin, lesson: dict, **body):
    return admin.post(
        f"{LESSONS}/{lesson['id']}/publish", json={"updated_at": lesson["updated_at"], **body}
    )


def test_an_ai_draft_needs_the_review_tick_on_its_first_publish(admin, db):
    lesson = _ai_draft(admin)

    for body in ({}, {"reviewed": False}):
        refused = _publish(admin, lesson, **body)
        assert refused.status_code == 409
        assert refused.json()["detail"] == {
            "code": "review_required",
            "message": "Tick “I have reviewed every card” before publishing an AI draft.",
        }
    assert outbox_events("content.lesson.") == []
    assert outbox_events("content.lesson_version.") == []

    published = _publish(admin, lesson, reviewed=True)
    assert published.status_code == 200, published.json()
    body = published.json()
    assert body["status"] == "published" and body["origin"] == "ai"
    assert body["ai_reviewed_at"] is not None
    assert db.get(Lesson, uuid.UUID(lesson["id"])).ai_reviewed_by == ADMIN_ID

    # Later publishes don't ask again, and keep the first review.
    edited = admin.patch(
        f"{LESSONS}/{lesson['id']}", json={"updated_at": body["updated_at"], "title": "New"}
    ).json()
    again = _publish(admin, edited)
    assert again.status_code == 200, again.json()
    assert again.json()["version"]["number"] == 2
    assert again.json()["ai_reviewed_at"] == body["ai_reviewed_at"]


def test_authored_lessons_publish_as_before(admin, db):
    topic = _topic(admin)
    lesson = _published(admin, topic, "Ordering kopi")
    assert lesson["origin"] == "authored"
    assert lesson["ai_reviewed_at"] is None
    assert db.get(Lesson, uuid.UUID(lesson["id"])).origin == LessonOrigin.AUTHORED


# --- Erasure --------------------------------------------------------------------------------


def test_a_deleted_admins_id_is_forgotten_on_jobs_and_reviews(admin, db):
    lesson = _ai_draft(admin)
    published = _publish(admin, lesson, reviewed=True).json()
    data = {"user_id": str(ADMIN_ID), "deleted_at": "2026-11-10T08:00:00Z"}
    envelope = make_envelope("identity.user.deleted", data, ADMIN_ID, 2)

    assert build_consumer().handle(json.dumps(envelope).encode()) is Outcome.ACK

    db.expire_all()
    row = db.get(Lesson, uuid.UUID(lesson["id"]))
    assert row.ai_reviewed_by is None
    assert row.ai_reviewed_at is not None
    assert row.updated_at == datetime.fromisoformat(published["updated_at"])  # not an edit
    assert db.scalars(select(GenerationJob.requested_by)).all() == [None]
