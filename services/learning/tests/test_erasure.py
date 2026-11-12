"""Deleting an account (identity.user.deleted): Learning erases everything it holds about
the learner, for good. New tests; in the monolith this was ON DELETE CASCADE from users."""

import pytest
from sqlalchemy import func, select

from app.models import (
    AptitudeAttempt,
    AttemptAnswer,
    ErasedLearner,
    GeneratedLesson,
    GeneratedLessonAttempt,
    GeneratedLessonReport,
    Learner,
    LessonAttempt,
    LessonCompletion,
    TopicExemption,
)
from tests.conftest import sign_in
from tests.support.records import complete, quiz


def _count(db, model, *where) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model).where(*where))


def _run(client, lesson):
    attempt = client.post(f"/api/lessons/{lesson.id}/attempts", json={"version": 1}).json()["id"]
    client.post(
        f"/api/attempts/{attempt}/answers", json={"question_id": "q1", "option_id": "wrong"}
    )
    assert client.post(f"/api/attempts/{attempt}/finish").status_code == 200


def _generated(db, user, topic) -> None:
    """A generated lesson with an attempt and a report (tests/test_generated.py plays one)."""
    row = GeneratedLesson(
        user_id=user.id,
        topic_id=topic.id,
        status="ready",
        focus="new",
        difficulty="right",
        length="short",
        level=1,
        brief={"topic": {"name": topic.name}},
        covers=[],
    )
    db.add(row)
    db.flush()
    db.add(GeneratedLessonAttempt(generated_lesson_id=row.id))
    db.add(GeneratedLessonReport(generated_lesson_id=row.id, card_id="c1", reason="typo"))
    db.commit()


@pytest.fixture
def world(client, db, content, make_user):
    topic = content.topic("Singlish")
    lesson = content.lesson(topic, "Lah")
    gone, kept = make_user("gone@example.com"), make_user("kept@example.com")
    for user in (gone, kept):
        sign_in(client, user)
        _run(client, lesson)
        quiz(db, user, {topic: 1})
        _generated(db, user, topic)
    complete(db, gone, content.lesson(topic, "Leh"))
    return gone, kept, lesson


def test_deleting_an_account_erases_the_learner_and_nobody_else(db, identity, world):
    gone, kept, _ = world
    identity.delete(gone)

    for model, column in (
        (LessonAttempt, LessonAttempt.user_id),
        (LessonCompletion, LessonCompletion.user_id),
        (AptitudeAttempt, AptitudeAttempt.user_id),
        (TopicExemption, TopicExemption.user_id),
        (Learner, Learner.user_id),
        (GeneratedLesson, GeneratedLesson.user_id),
    ):
        assert _count(db, model, column == gone.id) == 0, model.__tablename__
        assert _count(db, model, column == kept.id) == 1, model.__tablename__
    assert _count(db, AttemptAnswer) == 1  # only the kept learner's answer
    assert _count(db, GeneratedLessonAttempt) == 1  # their attempts and reports go with them
    assert _count(db, GeneratedLessonReport) == 1
    assert _count(db, ErasedLearner, ErasedLearner.user_id == gone.id) == 1


def test_erasing_twice_is_harmless(db, bus, identity, world):
    gone, _, _ = world
    deleted = identity.delete(gone)
    bus.deliver(deleted)
    assert _count(db, ErasedLearner) == 1


def test_a_replayed_registration_never_brings_an_erased_learner_back(db, bus, identity, world):
    gone, _, _ = world
    registered = next(
        e
        for e in bus.sent
        if e["type"] == "identity.user.registered" and e["aggregate_id"] == str(gone.id)
    )
    identity.delete(gone)
    bus.deliver(registered)

    assert _count(db, Learner, Learner.user_id == gone.id) == 0


def test_a_deletion_that_overtakes_the_registration_still_wins(db, identity, make_user, bus):
    """Out of order: user.deleted (v2) arrives before user.registered (v1)."""
    from tests.support.identity import User, user_id_for

    late = User(user_id_for("late@example.com"), "late@example.com", "Late", "user", "newcomer")
    identity.delete(late)
    identity.register("late@example.com")

    assert _count(db, Learner, Learner.user_id == late.id) == 0
    assert _count(db, ErasedLearner, ErasedLearner.user_id == late.id) == 1


def test_a_request_in_flight_after_erasure_creates_nothing(client, db, content, identity, world):
    """The gateway stops the deleted user's session at once; a request that was already on
    its way is refused by the tombstone instead of writing rows nobody would erase."""
    gone, _, lesson = world
    identity.delete(gone)
    sign_in(client, gone)

    response = client.post(f"/api/lessons/{lesson.id}/attempts", json={"version": 1})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_signed_in"
    assert _count(db, LessonAttempt, LessonAttempt.user_id == gone.id) == 0


def test_an_erased_learners_quiz_submission_is_refused(client, db, content, identity, make_user):
    topic = content.topic("Hawker")
    content.full_bank([topic])
    user = make_user("quiz@example.com")
    sign_in(client, user)
    question = client.post("/api/aptitude/start").json()["question"]
    answers = [{"question_id": question["id"], "option_id": "not-sure"}]
    identity.delete(user)

    response = client.post("/api/aptitude/submit", json={"answers": answers})
    assert response.status_code == 401
    assert _count(db, AptitudeAttempt) == 0


def test_erased_learners_progress_reads_empty(client, content, identity, world):
    gone, _, _ = world
    identity.delete(gone)
    sign_in(client, gone)
    body = client.get("/api/progress").json()
    assert (body["completed"], body["aptitude_taken"]) == (0, False)
