"""SCRUM-84: administrators see how learners do on each version of a lesson, never for fewer
than 5 learners, and never by name."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app import insights
from app.models import (
    AttemptAnswer,
    Lesson,
    LessonAttempt,
    LessonStatus,
    LessonVersion,
    Topic,
    UserRole,
    UserType,
)
from app.problems import ContentProblem

ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)

DOC = {
    "cards": [
        {"id": "intro", "text": "**Meh** questions something."},
        {
            "id": "c1",
            "text": "Really free {{blank}}?",
            "question": {
                "id": "q1",
                "options": [
                    {"id": "meh", "text": "meh", "correct": True},
                    {"id": "lah", "text": "lah"},
                    {"id": "lor", "text": "lor"},
                ],
                "explanation": "Meh marks doubt.",
            },
        },
        {
            "id": "c2",
            "text": "Can meh? means they {{blank}}.",
            "question": {
                "id": "q2",
                "options": [
                    {"id": "doubt", "text": "doubt it", "correct": True},
                    {"id": "agree", "text": "agree"},
                ],
                "explanation": "Meh marks doubt.",
            },
        },
        {
            "id": "c3",
            "text": "Say {{blank}}.",
            "question": {
                "id": "tap",
                "options": [{"id": "ok", "text": "thank you"}],
                "explanation": "Politeness.",
            },
        },
    ]
}
RIGHT = {"q1": "meh", "q2": "doubt", "tap": "ok"}


@pytest.fixture
def lesson(db) -> Lesson:
    topic = Topic(name="Singlish")
    lesson = Lesson(title="Lah, Leh and Lor", topic=topic, draft=DOC)
    db.add(lesson)
    db.commit()
    _publish(db, lesson)
    return lesson


def _publish(db, lesson: Lesson, doc=DOC) -> LessonVersion:
    version = LessonVersion(
        lesson_id=lesson.id,
        number=len(lesson.versions) + 1,
        title=lesson.title,
        summary="",
        doc=doc,
        published_at=NOW - timedelta(days=60),
    )
    lesson.status = LessonStatus.PUBLISHED
    db.add(version)
    db.commit()
    db.refresh(lesson)
    return version


@pytest.fixture
def learners(make_user):
    """Make n learners; the first `singaporeans` of them are Singaporeans."""

    def _make(n: int, singaporeans: int = 0, start: int = 0):
        made = []
        for i in range(start, start + n):
            user = make_user(f"learner{i}@example.com", name=f"Learner Number{i}")
            if i - start < singaporeans:
                user.user_type = UserType.SINGAPOREAN
            made.append(user)
        return made

    return _make


def _run(db, user, version, answers=None, at=NOW - timedelta(days=1), finished=True):
    """One run through the version, answering `answers` (all right by default)."""
    answers = answers if answers is not None else RIGHT
    correct = {"q1": "meh", "q2": "doubt"}
    attempt = LessonAttempt(
        user_id=user.id,
        lesson_id=version.lesson_id,
        version_id=version.id,
        started_at=at - timedelta(minutes=2),
    )
    db.add(attempt)
    db.flush()
    for question_id, option_id in answers.items():
        scored = question_id != "tap"
        db.add(
            AttemptAnswer(
                attempt_id=attempt.id,
                question_id=question_id,
                option_id=option_id,
                correct=not scored or correct[question_id] == option_id,
                scored=scored,
                answered_at=at - timedelta(minutes=1),
            )
        )
    if finished:
        attempt.finished_at = at
        attempt.scored = 2
        attempt.correct = sum(answers.get(q) == o for q, o in correct.items())
    db.commit()
    return attempt


def _insights(db, lesson, **kwargs) -> insights.LessonInsights:
    return insights.lesson_insights(db, lesson.id, now=NOW, **kwargs)


def _question(result, question_id):
    return next(q for q in result.questions if q.id == question_id)


# --- AC3: nothing for fewer than 5 learners ------------------------------------------------


def test_no_figures_until_five_learners_have_finished(db, lesson, learners):
    version = lesson.versions[0]
    people = learners(5)
    for user in people[:4]:
        _run(db, user, version)
    # Started but not finished: does not count towards the five.
    _run(db, people[4], version, answers={"q1": "meh"}, finished=False)

    result = _insights(db, lesson)
    assert result.enough is False
    assert result.summary is result.questions is result.funnel is result.scores is None
    assert result.trend.series == []

    _run(db, people[4], version)
    result = _insights(db, lesson)
    assert result.enough is True
    assert result.summary.learners == 5


def test_a_lesson_never_published_has_no_versions(db, learners):
    lesson = Lesson(title="Draft", draft=DOC)
    db.add(lesson)
    db.commit()
    result = _insights(db, lesson)
    assert result.versions == [] and result.version is None and result.enough is False


def test_administrators_never_count(db, lesson, learners, make_user):
    version = lesson.versions[0]
    for user in learners(4):
        _run(db, user, version)
    _run(db, make_user("staff@example.com", role=UserRole.ADMIN), version)
    assert _insights(db, lesson).enough is False


# --- AC1 and AC2: learners, scores and each question ---------------------------------------


def test_summary_learners_average_best_and_finish_rate(db, lesson, learners):
    version = lesson.versions[0]
    people = learners(5)
    _run(db, people[0], version, {"q1": "lah", "q2": "agree", "tap": "ok"}, at=NOW - timedelta(3))
    _run(db, people[0], version, at=NOW - timedelta(2))  # a better retake: best is 2 of 2
    _run(db, people[1], version, {"q1": "lah", "q2": "doubt", "tap": "ok"})  # 1 of 2
    for user in people[2:]:
        _run(db, user, version)
    _run(db, people[4], version, {"q1": "meh"}, finished=False)  # an abandoned retake

    summary = _insights(db, lesson).summary
    assert summary.learners == 5
    assert summary.average_best == 0.9  # (1 + 0.5 + 1 + 1 + 1) / 5
    # First runs only: 0 + 1 + 2 + 2 + 2 right, of 10.
    assert summary.right_first_time == 0.7
    assert summary.finish_rate == round(6 / 7, 4)
    assert summary.share_of_learners == 1.0
    assert summary.previous is None


def test_questions_use_each_learners_first_run(db, lesson, learners):
    version = lesson.versions[0]
    people = learners(5)
    # Two pick "lah" first, then fix it on a retake; the retakes must not change the figures.
    for user in people[:2]:
        _run(db, user, version, {"q1": "lah", "q2": "doubt", "tap": "ok"}, at=NOW - timedelta(3))
        _run(db, user, version, at=NOW - timedelta(2))
    _run(db, people[2], version, {"q1": "lor", "q2": "agree", "tap": "ok"})
    for user in people[3:]:
        _run(db, user, version)

    result = _insights(db, lesson)
    q1 = _question(result, "q1")
    assert q1.right_first_time == 0.4
    assert {o.id: o.chosen for o in q1.options} == {"meh": 0.4, "lah": 0.4, "lor": 0.2}
    assert [o.correct for o in q1.options] == [True, False, False]
    assert (q1.number, q1.card_number, q1.text) == (1, 2, "Really free {{blank}}?")
    assert _question(result, "q2").right_first_time == 0.8
    # Fewer than 5 retook q1, so its retake figure is hidden.
    assert q1.fixed_on_retake is None


def test_one_option_taps_are_not_listed(db, lesson, learners):
    version = lesson.versions[0]
    for user in learners(5):
        _run(db, user, version)
    assert [q.id for q in _insights(db, lesson).questions] == ["q1", "q2"]


def test_fixed_on_retake_needs_five_who_retook(db, lesson, learners):
    version = lesson.versions[0]
    people = learners(6)
    wrong = {"q1": "lah", "q2": "doubt", "tap": "ok"}
    for i, user in enumerate(people[:5]):
        _run(db, user, version, wrong, at=NOW - timedelta(3))
        # Four of the five get it right on the retake.
        _run(db, user, version, RIGHT if i < 4 else wrong, at=NOW - timedelta(2))
    _run(db, people[5], version, wrong)  # wrong, never retook: not in the figure

    assert _question(_insights(db, lesson), "q1").fixed_on_retake == 0.8


def test_funnel_and_score_spread(db, lesson, learners):
    version = lesson.versions[0]
    people = learners(5)
    _run(db, people[0], version, {"q1": "lah", "q2": "agree", "tap": "ok"})
    _run(db, people[1], version, {"q1": "lah", "q2": "doubt", "tap": "ok"})
    for user in people[2:]:
        _run(db, user, version)
    _run(db, people[0], version, {"q1": "meh"}, finished=False)
    _run(db, people[1], version, {"q1": "meh", "q2": "doubt"}, finished=False)

    result = _insights(db, lesson)
    assert [(s.question, s.runs) for s in result.funnel] == [(1, 7), (2, 6), (3, 5), (None, 5)]
    assert [(s.correct, s.learners) for s in result.scores] == [(0, 1), (1, 1), (2, 3)]


# --- AC4: one version at a time ------------------------------------------------------------


def test_figures_are_per_version_and_compared_with_the_one_before(db, lesson, learners):
    first = lesson.versions[0]
    second = _publish(db, lesson)
    for user in learners(5):
        _run(db, user, first, {"q1": "lah", "q2": "doubt", "tap": "ok"}, at=NOW - timedelta(20))
    for user in learners(5, start=5):
        _run(db, user, second)

    latest = _insights(db, lesson)
    assert latest.version == 2
    assert [v.number for v in latest.versions] == [2, 1]
    assert latest.summary.learners == 5
    assert latest.summary.right_first_time == 1.0
    assert latest.summary.previous.number == 1
    assert latest.summary.previous.right_first_time == 0.5
    assert _question(latest, "q1").previous_right_first_time == 0.0

    older = _insights(db, lesson, version_number=1)
    assert older.summary.right_first_time == 0.5 and older.summary.previous is None


def test_an_unknown_version_or_lesson_is_not_found(db, lesson):
    with pytest.raises(ContentProblem) as refused:
        _insights(db, lesson, version_number=9)
    assert refused.value.code == "version_not_found"
    with pytest.raises(ContentProblem) as refused:
        insights.lesson_insights(db, uuid.uuid4())
    assert refused.value.code == "lesson_not_found"


def test_the_trend_runs_week_by_week_for_each_version(db, lesson, learners):
    first = lesson.versions[0]
    second = _publish(db, lesson)
    # Version 1: five learners in the week of 5 Oct; version 2: five in the week of 19 Oct.
    for user in learners(5):
        _run(db, user, first, at=datetime(2026, 10, 7, 4, tzinfo=UTC))
    for user in learners(5, start=5):
        _run(db, user, second, at=datetime(2026, 10, 21, 4, tzinfo=UTC))

    trend = _insights(db, lesson).trend
    assert [str(w) for w in trend.weeks] == ["2026-10-05", "2026-10-12", "2026-10-19"]
    by_version = {s.version: s for s in trend.series}
    assert by_version[1].finished == [5, None, None]
    assert by_version[1].average_best == [1.0, None, None]
    assert by_version[2].finished == [None, None, 5]
    assert by_version[2].right_first_time == [None, None, 1.0]


# --- Kinds of learner ----------------------------------------------------------------------


def test_newcomers_and_singaporeans_each_need_five(db, lesson, learners):
    version = lesson.versions[0]
    people = learners(9, singaporeans=5)
    for user in people[:5]:
        _run(db, user, version)
    for user in people[5:]:
        _run(db, user, version, {"q1": "lah", "q2": "doubt", "tap": "ok"})

    q1 = _question(_insights(db, lesson), "q1")
    assert q1.singaporeans == 1.0
    assert q1.newcomers is None  # only four newcomers

    only_singaporeans = _insights(db, lesson, learners="singaporean")
    assert only_singaporeans.summary.learners == 5
    assert _question(only_singaporeans, "q1").singaporeans is None  # not split again
    assert _insights(db, lesson, learners="newcomer").enough is False


# --- The route -----------------------------------------------------------------------------


@pytest.fixture
def admin(client, make_user):
    make_user(ADMIN["email"], ADMIN["password"], role=UserRole.ADMIN)
    assert client.post("/api/admin/auth/sign-in", json=ADMIN).status_code == 200
    return client


def test_the_page_names_no_learner(db, lesson, learners, admin):
    version = lesson.versions[0]
    people = learners(5)
    for user in people:
        _run(db, user, version)

    response = admin.get(f"/api/admin/lessons/{lesson.id}/insights")
    assert response.status_code == 200
    body = response.text
    assert response.json()["summary"]["learners"] == 5
    for user in people:
        assert user.email not in body and "Number" not in body and str(user.id) not in body


def test_the_route_refuses_unknown_versions_and_non_admins(db, lesson, client, admin):
    assert admin.get(f"/api/admin/lessons/{lesson.id}/insights?version=4").status_code == 404
    assert admin.get(f"/api/admin/lessons/{lesson.id}/insights?learners=x").status_code == 422
    admin.cookies.clear()
    assert client.get(f"/api/admin/lessons/{lesson.id}/insights").status_code == 401
