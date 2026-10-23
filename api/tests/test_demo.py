"""The demo-activity command (SCRUM-84): demo learners and their runs, so lesson insights
have something to show. It can be run again, and touches nobody else's data."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app import insights
from app.demo import DOMAIN, NEWCOMERS, SINGAPOREANS, demo_activity
from app.models import Lesson, LessonAttempt, LessonCompletion, LessonStatus, User, UserType
from app.seed import seed

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


def _count(db, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_demo_learners_give_every_published_lesson_figures(db):
    seed(db)
    real_users = _count(db, User)
    real_completions = _count(db, LessonCompletion)

    demo_activity(db, now=NOW)

    demo = User.email.like(f"%@{DOMAIN}")
    assert _count(db, User, demo, User.user_type == UserType.NEWCOMER) == NEWCOMERS
    assert _count(db, User, demo, User.user_type == UserType.SINGAPOREAN) == SINGAPOREANS
    assert _count(db, User) == real_users + NEWCOMERS + SINGAPOREANS
    attempts = db.scalars(select(LessonAttempt)).all()
    assert attempts and all(a.started_at <= NOW for a in attempts)
    assert any(a.finished_at is None for a in attempts)  # some learners stop half way

    # Every published lesson has enough learners on its latest version to show figures.

    for lesson in db.scalars(select(Lesson).where(Lesson.status == LessonStatus.PUBLISHED)):
        assert insights.lesson_insights(db, lesson.id, now=NOW).enough, lesson.title

    # The confusing question planted for the demo shows up as one.
    lah = db.scalar(select(Lesson).where(Lesson.title == "Lah, Leh and Lor"))
    result = insights.lesson_insights(db, lah.id, learners="newcomer", now=NOW)
    second = next(q for q in result.questions if q.number == 2)
    wrong = max((o for o in second.options if not o.correct), key=lambda o: o.chosen)
    assert wrong.text == "They fully agree"
    assert second.right_first_time < 0.6

    # Running it again replaces the demo data instead of adding to it.
    completions = _count(db, LessonCompletion)
    demo_activity(db, now=NOW)
    assert _count(db, User) == real_users + NEWCOMERS + SINGAPOREANS
    assert _count(db, LessonCompletion) == completions
    assert (
        _count(db, LessonCompletion, ~LessonCompletion.user_id.in_(select(User.id).where(demo)))
        == real_completions
    )
