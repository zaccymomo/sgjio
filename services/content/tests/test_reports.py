"""SCRUM-82: a learner reports a problem on one card of a lesson, naming the lesson, the
version and the card it was sent from. SCRUM-83: administrators see the open reports and
mark them Fixed or Dismissed."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import (
    Lesson,
    LessonReport,
    LessonStatus,
    LessonVersion,
    ReportStatus,
    Topic,
)

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


# --- Administrators (SCRUM-83) -------------------------------------------------------------


def _open(admin) -> list[dict]:
    response = admin.get("/api/admin/reports")
    assert response.status_code == 200
    return response.json()


def test_reports_are_for_administrators_only(learner, lesson):
    assert learner.get("/api/admin/reports").status_code == 401


def test_open_reports_newest_first_with_what_the_page_needs(admin, learner, lesson):
    """AC1: lesson, card, reason, note and date, and nothing about who sent it."""
    _report(learner, lesson, card_id="intro", reason="typo", note="Kopi is misspelt.")
    _report(learner, lesson, card_id="c1", reason="wrong")

    first, second = _open(admin)
    assert (first["card_id"], second["card_id"]) == ("c1", "intro")
    assert second == {
        "id": second["id"],
        "lesson_id": str(lesson.id),
        "lesson_title": "Ordering kopi",
        "topic_name": "Hawker & Food",
        "version": 1,
        "card_id": "intro",
        "card_number": 1,
        "card_excerpt": "Kopi is coffee with condensed milk.",
        "card_in_draft": True,
        "reason": "typo",
        "note": "Kopi is misspelt.",
        "status": "open",
        "created_at": second["created_at"],
        "resolved_at": None,
    }
    assert first["card_excerpt"] == "Black coffee with sugar is kopi ___."


def test_a_report_says_when_its_card_has_left_the_draft(db, admin, learner, lesson):
    """AC2: the editor opens the card by id, so the page needs to know it is still there."""
    _report(learner, lesson, card_id="intro")
    lesson.draft = {"cards": DOC["cards"][1:]}
    db.commit()

    [report] = _open(admin)
    assert report["card_in_draft"] is False
    assert report["card_number"] == 1  # still its place in the version reported


@pytest.mark.parametrize("status", ["fixed", "dismissed"])
def test_marking_a_report_takes_it_off_the_open_list_and_keeps_it(
    db, admin, learner, lesson, status
):
    """AC3."""
    _report(learner, lesson)
    [report] = _open(admin)

    response = admin.put(f"/api/admin/reports/{report['id']}/status", json={"status": status})
    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()["resolved_at"] is not None

    assert _open(admin) == []
    [kept] = admin.get("/api/admin/reports?status=closed").json()
    assert (kept["id"], kept["status"]) == (report["id"], status)
    [row] = _reports(db)
    assert row.resolved_by is not None


def test_a_report_can_be_reopened(admin, learner, lesson):
    _report(learner, lesson)
    [report] = _open(admin)
    admin.put(f"/api/admin/reports/{report['id']}/status", json={"status": "dismissed"})

    response = admin.put(f"/api/admin/reports/{report['id']}/status", json={"status": "open"})
    assert response.json()["resolved_at"] is None
    assert [r["id"] for r in _open(admin)] == [report["id"]]


def test_an_unknown_report_or_status_is_refused(admin):
    missing = "00000000-0000-0000-0000-000000000000"
    response = admin.put(f"/api/admin/reports/{missing}/status", json={"status": "fixed"})
    assert (response.status_code, response.json()["detail"]["code"]) == (404, "report_not_found")
    assert admin.get("/api/admin/reports?status=everything").status_code == 422


def test_the_lesson_list_counts_each_lessons_open_reports(admin, learner, lesson):
    """AC4."""
    _report(learner, lesson)
    _report(learner, lesson, card_id="intro")
    [row] = admin.get("/api/admin/lessons").json()
    assert row["open_reports"] == 2

    [report, _] = _open(admin)
    admin.put(f"/api/admin/reports/{report['id']}/status", json={"status": "fixed"})
    [row] = admin.get("/api/admin/lessons").json()
    assert row["open_reports"] == 1
