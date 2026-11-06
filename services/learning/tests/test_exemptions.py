"""SCRUM-113: per-topic exemptions. (Ported from api/tests/test_exemptions.py.)

Each user has at most one completed aptitude quiz and, from it, one exemption level (0 to
5) per topic. Exempted lessons are worked out from that and each lesson's level.

Dropped from the monolith's file: the migration tests (0015 -> 0016 and its rollback),
which test the monolith's own history; Learning starts from a fresh baseline.
"""

import uuid

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.db import engine
from app.exemptions import exempted_lessons, exemption_levels, is_exempted
from app.models import AptitudeAttempt, LearnableLesson, TopicExemption
from tests.support.records import quiz

# --- AC1: the exemption table exists --------------------------------------------------------


def test_the_exemption_table_exists():
    schema = inspect(engine)
    assert "level" not in {c["name"] for c in schema.get_columns("aptitude_attempts")}
    assert {c["name"] for c in schema.get_columns("topic_exemptions")} == {
        "user_id",
        "topic_id",
        "level",
    }
    referred = {
        (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in schema.get_foreign_keys("topic_exemptions")
    }
    # Users and topics belong to Identity and Content: plain UUIDs, no foreign keys.
    assert referred == {(("user_id",), "aptitude_attempts")}
    assert schema.get_pk_constraint("topic_exemptions")["constrained_columns"] == [
        "user_id",
        "topic_id",
    ]


# --- AC2: one exemption per topic, one completed quiz per user ---------------------------


def test_a_user_has_at_most_one_exemption_per_topic(db, content, make_user):
    user = make_user()
    topic = content.topic()
    quiz(db, user, {topic: 2})
    with pytest.raises(IntegrityError):
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=3))
        db.commit()


def test_a_user_can_be_exempted_in_several_topics(db, content, make_user):
    user = make_user()
    singlish = content.topic("Singlish", position=0)
    hawker = content.topic("Hawker culture", position=1)
    quiz(db, user, {singlish: 0, hawker: 4})
    assert exemption_levels(db, user.id) == {singlish.id: 0, hawker.id: 4}


def test_a_user_has_at_most_one_completed_quiz(db, make_user):
    user = make_user()
    quiz(db, user)
    with pytest.raises(IntegrityError):
        db.add(AptitudeAttempt(user_id=user.id, results=[]))
        db.commit()


def test_exemptions_cannot_exist_without_a_completed_quiz(db, content, make_user):
    user = make_user()
    topic = content.topic()
    with pytest.raises(IntegrityError):
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=1))
        db.commit()


def test_another_users_exemptions_are_not_theirs(db, content, make_user):
    user = make_user()
    other = make_user("other@example.com")
    quiz(db, other, {content.topic(): 3})
    assert exemption_levels(db, user.id) == {}


def test_deleting_an_account_deletes_its_quiz_and_exemptions(db, content, identity, make_user):
    """Was a cascade from `users`; now identity.user.deleted erases them."""
    user = make_user()
    quiz(db, user, {content.topic(): 2})
    identity.delete(user)
    assert db.scalar(select(AptitudeAttempt)) is None
    assert db.scalar(select(TopicExemption)) is None


# --- AC3: an exemption level outside 0 to 5 is rejected ----------------------------------


@pytest.mark.parametrize("level", [None, -1, 6])
def test_an_exemption_outside_0_to_5_is_rejected(db, content, make_user, level):
    user = make_user()
    topic = content.topic()
    quiz(db, user)
    with pytest.raises(IntegrityError):
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=level))
        db.commit()


@pytest.mark.parametrize("level", [0, 5])
def test_exemptions_of_0_and_5_are_accepted(db, content, make_user, level):
    user = make_user()
    topic = content.topic()
    quiz(db, user, {topic: level})
    assert exemption_levels(db, user.id) == {topic.id: level}


# --- AC5: exempted lessons are worked out, not stored ------------------------------------


def test_exempted_lessons_come_from_the_topic_exemption_and_lesson_levels(db, content, make_user):
    user = make_user()
    singlish = content.topic("Singlish", position=0)
    hawker = content.topic("Hawker culture", position=1)
    level_1 = content.lesson(singlish, "Singlish 1", level=1)
    level_2 = content.lesson(singlish, "Singlish 2", level=2)
    content.lesson(singlish, "Singlish 3", level=3)
    content.lesson(singlish, "Singlish 1 draft", level=1, status="draft")
    content.lesson(hawker, "Hawker 1", level=1)
    quiz(db, user, {singlish: 2, hawker: 0})

    assert set(db.scalars(exempted_lessons(user.id))) == {level_1.id, level_2.id}

    # A lesson published later at an exempted level is exempted too (SCRUM-104 AC3).
    later = content.lesson(singlish, "Singlish 2, later", level=2)
    assert later.id in set(db.scalars(exempted_lessons(user.id)))

    exempt = dict(
        db.execute(
            select(LearnableLesson.display_title, is_exempted(user.id)).order_by(
                LearnableLesson.display_title
            )
        ).all()
    )
    assert exempt["Singlish 3"] is False
    assert exempt["Hawker 1"] is False


def test_a_withdrawn_lesson_is_not_exempted(db, content, make_user):
    user = make_user()
    topic = content.topic()
    lesson = content.lesson(topic, "Level 1", level=1)
    quiz(db, user, {topic: 3})
    content.withdraw(lesson)
    assert list(db.scalars(exempted_lessons(user.id))) == []


def test_a_user_who_skipped_the_quiz_is_exempted_from_nothing(db, content, make_user):
    user = make_user()
    content.lesson(content.topic(), "Level 1", level=1)
    assert exemption_levels(db, user.id) == {}
    assert list(db.scalars(exempted_lessons(user.id))) == []


def test_an_unknown_user_has_no_exemptions(db):
    assert exemption_levels(db, uuid.uuid4()) == {}
