"""What Content tells the other services (contracts/README.md, docs/architecture/
detailed-plan.md section 2.2): which change sends which event, at which version, saying what.

Every event any test writes is also checked against its schema in contracts/events, and
each aggregate's versions are checked to rise, by conftest.events_follow_the_contract.
"""

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app import events, projections
from app.consumers import build_consumer
from app.models import (
    AptitudeQuestion,
    Lesson,
    LessonReport,
    LessonStatus,
    LessonVersion,
    MediaAsset,
    MediaKind,
    ReportReason,
    Topic,
)
from app.platform.consumer import Outcome
from app.platform.testing import make_envelope
from tests.conftest import ADMIN_ID, event_types, outbox_events

TOPICS = "/api/admin/topics"
LESSONS = "/api/admin/lessons"
QUESTIONS = "/api/admin/aptitude-questions"
BANK_ID = "d69a3dc8-6470-5484-a156-901c82a34f06"

READY_DOC = {
    "cards": [
        {"id": "intro", "text": "**Kopi** is coffee with _condensed_ milk."},
        {
            "id": "c1",
            "text": "Black coffee with sugar is kopi {{blank}}.",
            "question": {
                "id": "q1",
                "options": [
                    {"id": "o", "text": "O", "correct": True},
                    {"id": "c", "text": "C", "why_not": "Milk."},
                ],
                "explanation": "O means no milk.",
            },
        },
        {
            "id": "c2",
            "text": "Say it: {{blank}}!",
            "question": {"id": "q2", "options": [{"id": "s", "text": "Shiok"}], "explanation": "."},
        },
    ]
}


def _topic(admin, name="Hawker & Food", **fields) -> dict:
    response = admin.post(TOPICS, json={"name": name, **fields})
    assert response.status_code == 201, response.json()
    return response.json()


def _lesson(admin, topic: dict | None, title="Ordering kopi", level=1, doc=READY_DOC) -> dict:
    body = {"title": title, "doc": doc, "level": level}
    body["topic_id"] = topic["id"] if topic else None
    response = admin.post(LESSONS, json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def _act(admin, lesson: dict, action: str) -> dict:
    response = admin.post(
        f"{LESSONS}/{lesson['id']}/{action}", json={"updated_at": lesson["updated_at"]}
    )
    assert response.status_code == 200, response.json()
    return response.json()


def _save(admin, lesson: dict, **changes) -> dict:
    response = admin.patch(
        f"{LESSONS}/{lesson['id']}", json={"updated_at": lesson["updated_at"], **changes}
    )
    assert response.status_code == 200, response.json()
    return response.json()


def _question(admin, topic: dict, level=1, **fields) -> dict:
    body = {
        "topic_id": topic["id"],
        "level": level,
        "prompt": "What do you say?",
        "options": [{"id": "a", "text": "Lah", "correct": True}, {"id": "b", "text": "Leh"}],
        **fields,
    }
    response = admin.post(QUESTIONS, json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def _new(since: int) -> list[tuple[str, str, int]]:
    """(type, aggregate_id, version) of the events written since `since`."""
    return [
        (e["type"], e["aggregate_id"], e["aggregate_version"]) for e in outbox_events(since=since)
    ]


# --- Topics ---------------------------------------------------------------------------------


def test_creating_a_topic_announces_it_at_version_1(admin):
    topic = _topic(admin, description="Kopi and more.")

    [event] = outbox_events()
    assert (event["type"], event["aggregate_id"], event["aggregate_version"]) == (
        "content.topic.changed",
        topic["id"],
        1,
    )
    assert event["producer"] == "content"
    assert event["aggregate_type"] == "topic"
    assert event["data"] == {
        "topic_id": topic["id"],
        "name": "Hawker & Food",
        "description": "Kopi and more.",
        "position": 0,
        "is_archived": False,
    }


def test_a_rename_also_announces_the_bank_and_a_new_description_only_the_topic(admin):
    topic = _topic(admin)
    sent = len(outbox_events())

    admin.patch(f"{TOPICS}/{topic['id']}", json={"name": "Hawker", "description": "New."})
    assert event_types(sent) == ["content.topic.changed", "content.aptitude_bank.changed"]

    sent = len(outbox_events())
    admin.patch(f"{TOPICS}/{topic['id']}", json={"name": "Hawker", "description": "Newer."})
    assert _new(sent) == [("content.topic.changed", topic["id"], 3)]

    sent = len(outbox_events())
    admin.patch(f"{TOPICS}/{topic['id']}", json={"name": "Hawker"})  # nothing changes
    assert _new(sent) == []


def test_a_name_clash_announces_nothing(admin):
    _topic(admin, "Singlish")
    other = _topic(admin, "Workplace")
    sent = len(outbox_events())
    assert admin.patch(f"{TOPICS}/{other['id']}", json={"name": "singlish"}).status_code == 409
    assert admin.post(TOPICS, json={"name": "SINGLISH"}).status_code == 409
    assert _new(sent) == []


def test_archive_and_restore_reach_the_topic_its_published_lessons_and_the_bank(admin, db):
    topic = _topic(admin)
    published = _act(admin, _lesson(admin, topic), "publish")
    withdrawn = _act(admin, _act(admin, _lesson(admin, topic, "Tables"), "publish"), "withdraw")
    draft = _lesson(admin, topic, "Draft")
    sent = len(outbox_events())

    admin.post(f"{TOPICS}/{topic['id']}/archive")

    new = outbox_events(since=sent)
    assert [e["type"] for e in new] == [
        "content.topic.changed",
        "content.lesson.changed",
        "content.lesson.changed",
        "content.aptitude_bank.changed",
    ]
    assert new[0]["data"]["is_archived"] is True
    lessons = {e["aggregate_id"]: e for e in new[1:3]}
    assert set(lessons) == {published["id"], withdrawn["id"]}  # never the draft
    assert all(not e["data"]["learner_visible"] for e in lessons.values())
    assert lessons[published["id"]]["data"]["publication_state"] == "published"
    # Not an edit: the editors' "last updated" stays, so nobody's open editor goes stale.
    db.expire_all()
    for lesson in (published, withdrawn, draft):
        stored = db.get(Lesson, lesson["id"])
        assert (
            stored.updated_at.isoformat()
            == datetime.fromisoformat(
                admin.get(f"{LESSONS}/{lesson['id']}").json()["updated_at"]
            ).isoformat()
        )
    assert _save(admin, published, summary="Still editable")["summary"] == "Still editable"

    sent = len(outbox_events())
    admin.post(f"{TOPICS}/{topic['id']}/archive")  # already archived: nothing
    assert _new(sent) == []

    admin.post(f"{TOPICS}/{topic['id']}/restore")
    new = outbox_events(since=sent)
    assert [e["type"] for e in new][0] == "content.topic.changed"
    visible = {e["aggregate_id"]: e["data"]["learner_visible"] for e in new[1:3]}
    assert visible == {published["id"]: True, withdrawn["id"]: False}


def test_deleting_a_topic_sends_a_tombstone_one_past_its_version(admin):
    topic = _topic(admin)
    admin.patch(f"{TOPICS}/{topic['id']}", json={"name": "Renamed"})  # version 2
    sent = len(outbox_events())

    assert admin.delete(f"{TOPICS}/{topic['id']}").status_code == 204

    [event] = outbox_events(since=sent)
    assert (event["type"], event["aggregate_version"]) == ("content.topic.deleted", 3)
    assert event["data"] == {"topic_id": topic["id"]}


def test_reordering_announces_only_the_topics_that_moved_then_the_bank(admin):
    a, b, c = (_topic(admin, name) for name in "ABC")
    sent = len(outbox_events())

    response = admin.put(
        f"{TOPICS}/order",
        json={"ids": [b["id"], a["id"], c["id"]], "previous_ids": [a["id"], b["id"], c["id"]]},
    )
    assert response.status_code == 200
    new = outbox_events(since=sent)
    assert [(e["type"], e["aggregate_id"]) for e in new] == [
        ("content.topic.changed", b["id"]),
        ("content.topic.changed", a["id"]),
        ("content.aptitude_bank.changed", BANK_ID),
    ]
    assert [e["data"]["position"] for e in new[:2]] == [0, 1]
    assert [e["aggregate_version"] for e in new[:2]] == [2, 2]

    sent = len(outbox_events())
    admin.put(
        f"{TOPICS}/order",
        json={"ids": [b["id"], a["id"], c["id"]], "previous_ids": [b["id"], a["id"], c["id"]]},
    )
    assert _new(sent) == []  # nothing moved


# --- Lessons --------------------------------------------------------------------------------


def test_drafts_never_published_are_never_announced(admin):
    topic = _topic(admin)
    sent = len(outbox_events())
    lesson = _lesson(admin, topic)
    lesson = _save(admin, lesson, title="Renamed draft", level=2)
    other = _topic(admin, "Other")
    sent_after_topic = len(outbox_events())
    _save(admin, lesson, topic_id=other["id"])
    admin.delete(
        f"{LESSONS}/{lesson['id']}",
        params={"updated_at": admin.get(f"{LESSONS}/{lesson['id']}").json()["updated_at"]},
    )
    assert [t for t in event_types(sent) if t.startswith("content.lesson")] == []
    assert _new(sent_after_topic) == []


def test_the_first_publish_sends_the_version_then_the_lesson(admin, db):
    topic = _topic(admin)
    lesson = _lesson(admin, topic, level=2)
    sent = len(outbox_events())

    body = _act(admin, lesson, "publish")

    version_event, lesson_event = outbox_events(since=sent)
    version = db.scalar(select(LessonVersion).where(LessonVersion.lesson_id == lesson["id"]))
    assert (version_event["type"], version_event["aggregate_id"]) == (
        "content.lesson_version.published",
        str(version.id),
    )
    assert version_event["aggregate_version"] == 1
    assert version.published_by == ADMIN_ID
    assert (lesson_event["type"], lesson_event["aggregate_version"]) == (
        "content.lesson.changed",
        1,
    )
    assert lesson_event["data"] == {
        "lesson_id": lesson["id"],
        "key": None,
        "topic_id": topic["id"],
        "level": 2,
        "position": 0,
        "created_at": lesson_event["data"]["created_at"],
        "display_title": "Ordering kopi",
        "publication_state": "published",
        "learner_visible": True,
        "first_published_at": version_event["data"]["published_at"],
        "published_at": version_event["data"]["published_at"],
        "withdrawn_at": None,
        "latest_version_id": str(version.id),
        "latest_version_number": 1,
    }
    assert datetime.fromisoformat(lesson_event["data"]["created_at"]) == datetime.fromisoformat(
        body["created_at"]
    )


def test_the_version_event_carries_what_learning_needs_to_grade_and_search(admin, db):
    image = MediaAsset(
        kind=MediaKind.IMAGE,
        mime="image/webp",
        sha256="a" * 64,
        data=b"x",
        size=1,
        width=4,
        height=3,
        placeholder="data:image/webp;base64,AA==",
        color="#aabbcc",
        filename="kopi.webp",
    )
    audio = MediaAsset(
        kind=MediaKind.AUDIO, mime="audio/wav", sha256="b" * 64, data=b"y", size=1,
        duration_ms=4_000, filename="hello.wav",
    )  # fmt: skip
    db.add_all([image, audio])
    db.commit()
    doc = json.loads(json.dumps(READY_DOC))
    doc["cards"][0]["image"] = {"asset_id": str(image.id), "alt": "A cup"}
    doc["cards"][0]["audio"] = {"asset_id": str(audio.id), "transcript": "Kopi"}
    lesson = _lesson(admin, _topic(admin), doc=doc)
    sent = len(outbox_events())

    _act(admin, lesson, "publish")

    data = outbox_events("content.lesson_version.published", since=sent)[0]["data"]
    stored = db.scalar(select(LessonVersion).where(LessonVersion.lesson_id == lesson["id"]))
    assert data["doc"] == stored.doc  # the stored document, unchanged
    assert data["questions"] == [
        {"card_id": "c1", "question_id": "q1", "scored": True, "correct_option_id": "o"},
        {"card_id": "c2", "question_id": "q2", "scored": False, "correct_option_id": "s"},
    ]
    assert data["scored_questions"] == 1
    # The editor's reading time, which already counts the 4 seconds of audio.
    assert lesson["stats"]["audio_seconds"] == 4
    assert data["reading_seconds"] == lesson["stats"]["reading_seconds"]
    assert data["cards_plain_text"] == [
        "Kopi is coffee with condensed milk.",
        "Black coffee with sugar is kopi ___.",
        "Say it: ___!",
    ]
    assert data["assets"][str(image.id)] == lesson["assets"][str(image.id)] | {
        "url": f"/api/media/{image.id}"
    }
    assert data["assets"][str(audio.id)]["duration_ms"] == 4_000
    assert set(data["assets"]) == {str(image.id), str(audio.id)}


def test_each_live_change_bumps_the_lesson_and_draft_edits_send_nothing(admin):
    topic = _topic(admin)
    other = _topic(admin, "Workplace")
    lesson = _act(admin, _lesson(admin, topic), "publish")
    sent = len(outbox_events())

    lesson = _save(admin, lesson, summary="New summary", doc=READY_DOC)
    assert _new(sent) == []  # learners keep the published version until a publish

    steps = [
        lambda lesson: _save(admin, lesson, title="Ordering kopi like a local"),  # title
        lambda lesson: _save(admin, lesson, topic_id=other["id"]),  # topic move
        lambda lesson: _act(admin, lesson, "withdraw"),
        lambda lesson: _act(admin, lesson, "restore"),
        lambda lesson: _act(admin, lesson, "publish"),  # a new version
        lambda lesson: _save(admin, lesson, title="Changed again"),
        lambda lesson: _act(admin, lesson, "discard"),  # the title goes back
    ]
    versions = []
    for step in steps:
        before = len(outbox_events())
        lesson = step(lesson)
        changes = outbox_events("content.lesson.changed", since=before)
        assert len(changes) == 1
        versions.append(changes[0]["aggregate_version"])
    assert versions == [2, 3, 4, 5, 6, 7, 8]
    last = outbox_events("content.lesson.changed")[-1]["data"]
    assert last["display_title"] == "Ordering kopi like a local"
    assert last["topic_id"] == other["id"]
    assert last["latest_version_number"] == 2

    sent = len(outbox_events())
    _act(admin, lesson, "publish")  # nothing new to publish
    _act(admin, lesson, "discard")  # nothing to discard
    assert _new(sent) == []


def test_reordering_announces_the_moved_published_lessons_only(admin, db):
    topic = _topic(admin)
    a = _act(admin, _lesson(admin, topic, "A"), "publish")
    b = _act(admin, _lesson(admin, topic, "B"), "publish")
    c = _lesson(admin, topic, "C")  # a draft
    sent = len(outbox_events())

    response = admin.put(
        f"{LESSONS}/order",
        json={
            "topic_id": topic["id"],
            "ids": [c["id"], b["id"], a["id"]],
            "previous_ids": [a["id"], b["id"], c["id"]],
        },
    )
    assert response.status_code == 200
    new = outbox_events(since=sent)
    # B stays at 1; the draft C moved too but was never published.
    assert [(e["aggregate_id"], e["data"]["position"]) for e in new] == [(a["id"], 2)]
    assert all(e["type"] == "content.lesson.changed" for e in new)
    # Moving is not editing: the open editor's "last updated" still works.
    assert _save(admin, a, summary="Fine")["summary"] == "Fine"


def test_a_publish_refused_for_blockers_announces_nothing(admin):
    lesson = _lesson(admin, None, title="")
    sent = len(outbox_events())
    response = admin.post(
        f"{LESSONS}/{lesson['id']}/publish", json={"updated_at": lesson["updated_at"]}
    )
    assert response.status_code == 409
    assert _new(sent) == []


# --- learner_visible: Content's one rule ----------------------------------------------------


@pytest.mark.parametrize(
    ("status", "topic", "visible"),
    [
        (LessonStatus.PUBLISHED, "active", True),
        (LessonStatus.PUBLISHED, "archived", False),
        (LessonStatus.PUBLISHED, None, False),
        (LessonStatus.WITHDRAWN, "active", False),
        (LessonStatus.WITHDRAWN, "archived", False),
        (LessonStatus.DRAFT, "active", False),
        (LessonStatus.DRAFT, None, False),
    ],
)
def test_learner_visible(status, topic, visible):
    archived_at = datetime.now(UTC) if topic == "archived" else None
    lesson = Lesson(title="A", status=status)
    the_topic = Topic(name="T", archived_at=archived_at) if topic else None
    assert projections.learner_visible(lesson, the_topic) is visible


# --- The aptitude bank ----------------------------------------------------------------------


def test_a_new_question_is_announced_then_the_bank(admin, db):
    topic = _topic(admin)
    sent = len(outbox_events())

    question = _question(admin, topic, level=2)

    new = outbox_events(since=sent)
    assert [e["type"] for e in new] == [
        "content.aptitude_question.changed",
        "content.aptitude_bank.changed",
    ]
    assert new[0]["aggregate_version"] == 1
    assert new[0]["data"] == {
        "question_id": question["id"],
        "topic_id": topic["id"],
        "level": 2,
        "prompt": "What do you say?",
        "options": [{"id": "a", "text": "Lah"}, {"id": "b", "text": "Leh"}],
        "correct_option_id": "a",
        "is_active": True,
        "seed_key": None,
    }
    assert (new[1]["aggregate_id"], new[1]["aggregate_version"]) == (BANK_ID, 1)
    assert new[1]["data"] == {"ready": False, "topics": [{"topic_id": topic["id"], "ready": False}]}
    db.expire_all()
    assert db.get(Topic, uuid.UUID(topic["id"])).assessed_at is not None


def test_question_edits_bump_its_version_and_the_banks_revision(admin):
    topic = _topic(admin)
    question = _question(admin, topic)
    url = f"{QUESTIONS}/{question['id']}"
    for change in ({"prompt": "Changed?"}, {"is_active": False}, {"is_active": True}):
        assert admin.patch(url, json=change).status_code == 200
    questions = outbox_events("content.aptitude_question.changed")
    banks = outbox_events("content.aptitude_bank.changed")
    assert [e["aggregate_version"] for e in questions] == [1, 2, 3, 4]
    assert [e["aggregate_version"] for e in banks] == [1, 2, 3, 4]
    assert questions[2]["data"]["is_active"] is False
    # No active question left: the topic is still assessed, and not ready.
    assert banks[2]["data"]["topics"] == [{"topic_id": topic["id"], "ready": False}]
    sent = len(outbox_events())
    assert admin.patch(url, json={"is_active": True}).status_code == 200  # no change
    assert _new(sent) == []


def test_the_bank_is_ready_with_an_active_question_at_every_level(admin):
    first = _topic(admin, "First")
    second = _topic(admin, "Second")
    for level in range(1, 6):
        _question(admin, second, level)
    for level in range(1, 6):
        _question(admin, first, level)
    bank = outbox_events("content.aptitude_bank.changed")[-1]["data"]
    assert bank == {
        "ready": True,
        "topics": [
            {"topic_id": first["id"], "ready": True},
            {"topic_id": second["id"], "ready": True},
        ],
    }
    # The quiz asks topics in the admin's order, so a reorder sends the bank again.
    admin.put(
        f"{TOPICS}/order",
        json={"ids": [second["id"], first["id"]], "previous_ids": [first["id"], second["id"]]},
    )
    bank = outbox_events("content.aptitude_bank.changed")[-1]["data"]
    assert [t["topic_id"] for t in bank["topics"]] == [second["id"], first["id"]]


def test_a_topic_that_ever_had_a_question_can_never_be_deleted(admin):
    old = _topic(admin, "Old")
    new = _topic(admin, "New")
    question = _question(admin, old)
    # Move its only question away: the topic is empty, but was assessed.
    moved = admin.patch(f"{QUESTIONS}/{question['id']}", json={"topic_id": new["id"]})
    assert moved.json()["topic_name"] == "New"

    response = admin.delete(f"{TOPICS}/{old['id']}")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "topic_not_empty",
        "message": "This topic has lessons, so it cannot be deleted. Archive it instead.",
    }
    assert "content.topic.deleted" not in event_types()


# --- identity.user.deleted ------------------------------------------------------------------


def _user_deleted(user_id: uuid.UUID) -> bytes:
    data = {"user_id": str(user_id), "deleted_at": "2026-11-10T08:00:00Z"}
    return json.dumps(make_envelope("identity.user.deleted", data, user_id, 2)).encode()


def test_a_deleted_users_ids_are_forgotten(db):
    gone, kept = uuid.uuid4(), uuid.uuid4()
    topic = Topic(name="T")
    lesson = Lesson(title="L", topic=topic, status=LessonStatus.PUBLISHED)
    version = LessonVersion(
        number=1, title="L", doc={"cards": []}, published_at=datetime.now(UTC), published_by=gone
    )
    lesson.versions.append(version)
    asset = MediaAsset(
        kind=MediaKind.AUDIO, mime="audio/wav", sha256="c" * 64, data=b"z", size=1,
        filename="a.wav", created_by=gone,
    )  # fmt: skip
    db.add_all([topic, lesson, asset])
    db.flush()
    reports = [
        LessonReport(lesson_id=lesson.id, version_id=version.id, card_id="c", reason=r, **who)
        for r, who in [
            (ReportReason.WRONG, {"reporter_id": gone}),
            (ReportReason.TYPO, {"reporter_id": kept, "resolved_by": gone}),
            (ReportReason.OTHER, {"reporter_id": kept, "resolved_by": kept}),
        ]
    ]
    db.add_all(reports)
    db.commit()
    consumer = build_consumer()

    assert consumer.handle(_user_deleted(gone)) is Outcome.ACK
    assert consumer.handle(_user_deleted(gone)) is Outcome.ACK  # again: same result

    db.expire_all()
    assert db.get(LessonVersion, version.id).published_by is None
    assert db.get(MediaAsset, asset.id).created_by is None
    rows = {r.reason: (r.reporter_id, r.resolved_by) for r in db.scalars(select(LessonReport))}
    assert rows == {
        ReportReason.WRONG: (None, None),
        ReportReason.TYPO: (kept, None),
        ReportReason.OTHER: (kept, kept),
    }
    assert db.get(LessonReport, reports[0].id) is not None  # the report itself is kept


def test_the_consumer_listens_only_for_deleted_users():
    consumer = build_consumer()
    assert consumer.queue == "content.events"
    assert consumer.routing_keys == ["identity.user.deleted"]
    other = make_envelope("identity.user.registered", {}, uuid.uuid4())
    assert consumer.handle(json.dumps(other).encode()) is Outcome.ACK
    assert consumer.handle(b"not json") is Outcome.REJECT


# --- republish-catalog ----------------------------------------------------------------------


@pytest.mark.repeats_versions
def test_republishing_repeats_the_current_state_at_current_versions(admin, db):
    topic = _topic(admin)
    lesson = _act(admin, _lesson(admin, topic), "publish")
    lesson = _act(admin, _save(admin, lesson, title="Second"), "publish")
    _lesson(admin, topic, "Draft")
    _question(admin, topic)
    before = outbox_events()
    latest = {}
    for event in before:
        latest[(event["type"].replace("deleted", "changed"), event["aggregate_id"])] = event

    counts = events.republish_catalog(db)
    db.commit()

    assert counts == {"topics": 1, "versions": 2, "lessons": 1, "questions": 1, "bank": 1}
    again = outbox_events(since=len(before))
    assert [e["type"] for e in again] == [
        "content.topic.changed",
        "content.lesson_version.published",
        "content.lesson_version.published",
        "content.lesson.changed",
        "content.aptitude_question.changed",
        "content.aptitude_bank.changed",
    ]
    for event in again:
        previous = latest[(event["type"], event["aggregate_id"])]
        assert event["aggregate_version"] == previous["aggregate_version"]
        assert event["data"] == previous["data"]


def test_republishing_an_empty_catalog_still_sends_the_bank(db):
    counts = events.republish_catalog(db)
    db.commit()
    assert counts["bank"] == 1
    [bank] = outbox_events()
    assert bank["data"] == {"ready": False, "topics": []}
    assert bank["aggregate_version"] == 1


# --- Correlation ----------------------------------------------------------------------------


def test_an_event_carries_the_request_id_that_caused_it(admin):
    admin.post(TOPICS, json={"name": "Singlish"}, headers={"X-Request-ID": "req-123"})
    [event] = outbox_events()
    assert event["correlation_id"] == "req-123"


def test_a_failed_change_writes_no_event(admin, db):
    topic = _topic(admin)
    db.add(AptitudeQuestion(
        topic_id=uuid.UUID(topic["id"]), level=1, prompt="?",
        options=[{"id": "a", "text": "A"}, {"id": "b", "text": "B"}], correct_option_id="a",
    ))  # fmt: skip
    db.commit()  # inserted by hand: assessed_at is not set, only the foreign key protects it
    sent = len(outbox_events())

    response = admin.delete(f"{TOPICS}/{topic['id']}")

    assert response.status_code == 409
    assert _new(sent) == []  # the tombstone rolled back with the delete
