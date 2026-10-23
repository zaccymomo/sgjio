"""SCRUM-82: a learner reports a problem on one card of a lesson, naming the lesson, the
version and the card it was sent from."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Lesson, LessonReport, LessonStatus, LessonVersion, ReportStatus, Topic

USER = {"email": "user@example.com", "password": "Password123"}

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
                    {"id": "c", "text": "C"},
                ],
                "explanation": "O means no milk.",
            },
        },
    ]
}


def _publish(db, lesson: Lesson, doc=DOC) -> LessonVersion:
    version = LessonVersion(
        lesson_id=lesson.id,
        number=len(lesson.versions) + 1,
        title=lesson.title,
        summary="",
        doc=doc,
        published_at=datetime.now(UTC),
    )
    lesson.status = LessonStatus.PUBLISHED
    db.add(version)
    db.commit()
    db.refresh(lesson)
    return version


@pytest.fixture
def lesson(db) -> Lesson:
    topic = Topic(name="Hawker & Food")
    lesson = Lesson(title="Ordering kopi", topic=topic, draft=DOC)
    db.add_all([topic, lesson])
    db.commit()
    _publish(db, lesson)
    return lesson


@pytest.fixture
def learner(client, make_user):
    make_user(**USER)
    assert client.post("/api/auth/sign-in", json=USER).status_code == 200
    return client


def _report(client, lesson, **changes):
    body = {"version": 1, "card_id": "c1", "reason": "wrong", "note": ""} | changes
    return client.post(f"/api/lessons/{lesson.id}/reports", json=body)


def _reports(db) -> list[LessonReport]:
    db.expire_all()
    return list(db.scalars(select(LessonReport)))


def test_reporting_needs_a_signed_in_user(client, lesson):
    assert _report(client, lesson).status_code == 401


def test_a_report_records_the_lesson_version_card_reason_and_note(db, learner, lesson):
    """AC1 to AC3."""
    response = _report(learner, lesson, reason="insensitive", note="  This reads as a stereotype. ")
    assert response.status_code == 201
    assert set(response.json()) == {"id", "created_at"}

    [report] = _reports(db)
    assert report.lesson_id == lesson.id
    assert report.version.number == 1
    assert report.card_id == "c1"
    assert report.reason.value == "insensitive"
    assert report.note == "This reads as a stereotype."
    assert report.status == ReportStatus.OPEN


@pytest.mark.parametrize("reason", ["wrong", "insensitive", "typo", "media", "other"])
def test_each_reason_from_the_story_is_accepted(learner, lesson, reason):
    assert _report(learner, lesson, reason=reason).status_code == 201


def test_any_card_can_be_reported_not_only_questions(db, learner, lesson):
    assert _report(learner, lesson, card_id="intro").status_code == 201


def test_the_note_is_optional_and_at_most_500_characters(db, learner, lesson):
    assert _report(learner, lesson, note="x" * 500).status_code == 201
    assert _report(learner, lesson, note="x" * 501).status_code == 422
    body = {"version": 1, "card_id": "c1", "reason": "typo"}
    assert learner.post(f"/api/lessons/{lesson.id}/reports", json=body).status_code == 201
    assert len(_reports(db)) == 2


def test_a_reason_is_required_and_must_be_one_of_the_list(db, learner, lesson):
    assert _report(learner, lesson, reason="boring").status_code == 422
    body = {"version": 1, "card_id": "c1"}
    assert learner.post(f"/api/lessons/{lesson.id}/reports", json=body).status_code == 422
    assert _reports(db) == []


def test_an_older_version_still_open_in_the_browser_can_be_reported(db, learner, lesson):
    _publish(db, lesson)
    assert _report(learner, lesson, version=1).status_code == 201
    assert _reports(db)[0].version.number == 1


def test_a_version_or_card_that_is_not_this_lessons_is_refused(db, learner, lesson):
    response = _report(learner, lesson, version=2)
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "version_not_found")
    response = _report(learner, lesson, card_id="nope")
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "card_not_found")
    assert _reports(db) == []


def test_a_lesson_learners_cannot_open_cannot_be_reported(db, learner, lesson):
    lesson.status = LessonStatus.WITHDRAWN
    db.commit()
    response = _report(learner, lesson)
    assert (response.status_code, response.json()["detail"]["code"]) == (404, "lesson_unavailable")
