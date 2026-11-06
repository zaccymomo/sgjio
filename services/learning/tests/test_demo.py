"""The demo-activity command (SCRUM-84): lesson runs for Identity's demo learners, so
lesson insights have something to show. (Ported from api/tests/test_demo.py; creating and
clearing the demo learners is Identity's seed-demo-learners and clear-demo-learners.)"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app import insights
from app.demo import (
    DEFAULT_COUNT,
    DemoLearnersMissing,
    demo_activity,
    demo_emails,
    demo_user_ids,
    newcomer_count,
)
from app.models import LearnableLesson, LessonAttempt, LessonCompletion
from tests.support.records import complete
from tests.support.seeded import seed_world

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
NONCE = "run1"


def _count(db, model, *where) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model).where(*where))


def _register_demo_learners(identity, nonce=NONCE, count=DEFAULT_COUNT):
    """What Identity's seed-demo-learners --count publishes: the first two thirds Newcomers."""
    users = []
    pairs = zip(demo_emails(count), demo_user_ids(nonce, count), strict=True)
    for n, (email, user_id) in enumerate(pairs):
        users.append(
            identity.register(
                email,
                user_type="singaporean" if n >= newcomer_count(count) else "newcomer",
                user_id=user_id,
            )
        )
    return users


def test_demo_learners_give_every_published_lesson_figures(db, content, identity):
    _, lessons = seed_world(content, identity)
    real_user = identity.register("real@example.com")
    complete(db, real_user, lessons["Lah, Leh and Lor"])
    demo = _register_demo_learners(identity)
    assert len(demo) == DEFAULT_COUNT == 60
    assert newcomer_count() == 40

    demo_activity(db, NONCE, now=NOW)

    attempts = db.scalars(select(LessonAttempt)).all()
    assert attempts and all(a.started_at <= NOW for a in attempts)
    assert any(a.finished_at is None for a in attempts)  # some learners stop half way
    demo_ids = {user.id for user in demo}
    assert {a.user_id for a in attempts} <= demo_ids

    # Every published lesson has enough learners on its latest version to show figures.
    for lesson in db.scalars(select(LearnableLesson)):
        assert insights.lesson_insights(db, lesson.id, now=NOW).enough, lesson.display_title

    # The confusing question planted for the demo shows up as one.
    lah = lessons["Lah, Leh and Lor"]
    result = insights.lesson_insights(db, lah.id, learners="newcomer", now=NOW)
    second = next(q for q in result.questions if q.number == 2)
    wrong = max((o for o in second.options if not o.correct), key=lambda o: o.chosen)
    assert wrong.text == "They fully agree"
    assert second.right_first_time < 0.6

    # Running it again replaces the demo data instead of adding to it.
    completions = _count(db, LessonCompletion)
    demo_activity(db, NONCE, now=NOW)
    assert _count(db, LessonCompletion) == completions
    assert _count(db, LessonCompletion, LessonCompletion.user_id == real_user.id) == 1


def test_clearing_the_demo_learners_erases_their_runs(db, content, identity):
    """Identity's clear-demo-learners sends user.deleted for each; Learning erases them."""
    seed_world(content, identity)
    demo = _register_demo_learners(identity)
    demo_activity(db, NONCE, now=NOW)
    for user in demo:
        identity.delete(user)
    assert _count(db, LessonAttempt) == 0
    assert _count(db, LessonCompletion) == 0


def test_a_new_run_uses_new_ids(content, identity):
    assert set(demo_user_ids("run1")).isdisjoint(demo_user_ids("run2"))


def test_demo_activity_waits_for_its_learners(db, content, identity):
    seed_world(content, identity)
    with pytest.raises(DemoLearnersMissing, match="0 of 60"):
        demo_activity(db, "never-registered", now=NOW, timeout=0.1)


def test_demo_activity_follows_identitys_count(db, content, identity):
    """seed-demo-learners --count 9 makes 6 Newcomers and 3 Singaporeans; demo-activity
    --count 9 waits for exactly those and gives only them runs."""
    seed_world(content, identity)
    demo = _register_demo_learners(identity, nonce="small", count=9)
    assert newcomer_count(9) == 6
    assert [u.email for u in demo][-1] == "learner09@demo.sgjio.example.com"

    demo_activity(db, "small", now=NOW, count=9)

    users = {a.user_id for a in db.scalars(select(LessonAttempt))}
    assert users and users <= {user.id for user in demo}
    with pytest.raises(DemoLearnersMissing, match="9 of 10"):
        demo_activity(db, "small", now=NOW, count=10, timeout=0.1)
