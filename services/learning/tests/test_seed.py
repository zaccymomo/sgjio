"""Learning's seed: the seed Newcomer's completions and the test personas' aptitude results,
found through the read models (contracts/README.md, "Seed and demo ids").
(Ported from the learner half of api/tests/test_seed.py and test_health_and_schema.py;
the topic, lesson and bank parts moved to Content, the accounts to Identity.)"""

import pytest
from sqlalchemy import func, select

from app import read_models
from app.db import SessionLocal
from app.models import AptitudeAttempt, LearnableTopic, LessonCompletion, TopicExemption
from app.seed import SEEDED_COMPLETIONS, TEST_USERS, SeedError, seed, user_id_for
from tests.conftest import sign_in
from tests.support.identity import User
from tests.support.seeded import seed_world


def test_seed_ids_are_identitys_deterministic_ids():
    import uuid

    assert user_id_for("Newcomer@SGJio.example.com ") == uuid.uuid5(
        uuid.NAMESPACE_URL, "sgjio:user:newcomer@sgjio.example.com"
    )


def test_seed_refuses_until_the_topics_have_arrived(db):
    with pytest.raises(SeedError, match="wait-for-read-models"):
        seed(db)


def test_seed_gives_the_newcomer_progress_in_every_circle_state(client, db, content, identity):
    seed_world(content, identity)
    log = seed(db)

    user = user_id_for("newcomer@sgjio.example.com")
    assert any("completed lesson(s) in Singlish" in line for line in log)
    count = db.scalar(
        select(func.count()).select_from(LessonCompletion).where(LessonCompletion.user_id == user)
    )
    # Each topic has 4 lessons, so every count in SEEDED_COMPLETIONS is met.
    assert count == sum(SEEDED_COMPLETIONS.values())

    sign_in(client, User(user, "newcomer@sgjio.example.com", "N", "user", "newcomer"))
    circles = {t["name"]: t["completed"] for t in client.get("/api/progress").json()["topics"]}
    assert circles == SEEDED_COMPLETIONS


def test_seeded_users_have_per_topic_placements_or_a_skipped_quiz(db, content, identity):
    seed_world(content, identity)
    seed(db)
    for email, expected in TEST_USERS.items():
        user_id = user_id_for(email)
        attempt = db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == user_id))
        exemptions = dict(
            db.execute(
                select(LearnableTopic.name, TopicExemption.level)
                .join(LearnableTopic, LearnableTopic.id == TopicExemption.topic_id)
                .where(TopicExemption.user_id == user_id)
            ).all()
        )
        if expected is None:
            assert attempt is None
            assert exemptions == {}
        else:
            assert attempt is not None
            assert exemptions == expected
            # One result per question asked: up to the first miss in each topic.
            assert len(attempt.results) == sum(
                5 if level == 5 else level + 1 for level in expected.values()
            )


def test_seeding_again_changes_nothing(db, content, identity):
    seed_world(content, identity)
    assert seed(db)
    assert seed(db) == []


def test_the_seed_never_overwrites_real_progress(db, content, identity):
    _, lessons = seed_world(content, identity)
    user = user_id_for("newcomer@sgjio.example.com")
    db.add(LessonCompletion(user_id=user, lesson_id=lessons["Lah, Leh and Lor"].id))
    db.commit()
    seed(db)
    assert (
        db.scalar(
            select(func.count())
            .select_from(LessonCompletion)
            .where(LessonCompletion.user_id == user)
        )
        == 1
    )


def test_waiting_for_read_models_ends_once_the_seeds_have_arrived(content, identity):
    messages: list[str] = []
    assert not read_models.wait(SessionLocal, 0.2, poll=0.05, say=messages.append)
    assert "topics Singlish" in messages[-1]

    seed_world(content, identity)
    assert read_models.wait(SessionLocal, 5, poll=0.05, say=messages.append)


def test_a_lesson_still_waiting_for_its_deck_keeps_the_wait_going(db, content, identity):
    seed_world(content, identity)
    lesson = content.lessons[0]
    content.publish(lesson, deliver_deck=False)
    assert read_models.missing(db) == ["the latest version of 1 lesson(s)"]
