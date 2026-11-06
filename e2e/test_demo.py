"""Lesson insights over the demo learners (detailed plan 8.3 item 11).

Needs `scripts/seed-all.sh --demo` (scripts/e2e.sh runs it): Identity's
seed-demo-learners and Learning's demo-activity, linked by the run nonce. Skipped when the
demo learners haven't been seeded.
"""

import pytest

from shapes import check

ROUTE = "GET /api/admin/lessons/{lesson_id}/insights"


def _seeded_lesson(admin, title: str) -> dict:
    lessons = check(admin.get("/api/admin/lessons"), "GET /api/admin/lessons", 200)
    found = [lesson for lesson in lessons if lesson["title"] == title]
    if not found:
        pytest.skip(f"seed lesson {title!r} not found")
    return found[0]


def test_demo_activity_fills_the_insights(admin):
    lesson = _seeded_lesson(admin, "Lah, Leh and Lor")
    body = check(admin.get(f"/api/admin/lessons/{lesson['id']}/insights"), ROUTE, 200)
    if not body["enough"]:
        pytest.skip("no demo activity: run scripts/seed-all.sh --demo")

    assert body["title"] == "Lah, Leh and Lor" and body["topic_name"] == "Singlish"
    assert body["learners"] == "all" and body["min_learners"] == 5
    summary = body["summary"]
    assert summary["learners"] >= 5
    assert 0 < summary["share_of_learners"] <= 1
    assert 0 <= summary["average_best"] <= 1 and 0 < summary["finish_rate"] <= 1
    assert body["questions"], body
    for question in body["questions"]:
        # The Newcomer / Singaporean split comes from Identity's user_type, replicated.
        assert question["newcomers"] is not None and question["singaporeans"] is not None
        assert abs(sum(option["chosen"] for option in question["options"]) - 1) < 0.01
    assert body["funnel"][0]["question"] == 1 and body["funnel"][-1]["question"] is None
    assert sum(score["learners"] for score in body["scores"]) == summary["learners"]
    assert body["trend"]["weeks"] and body["trend"]["series"]

    for kind in ("newcomer", "singaporean"):
        split = check(
            admin.get(f"/api/admin/lessons/{lesson['id']}/insights", params={"learners": kind}),
            ROUTE,
            200,
        )
        assert split["learners"] == kind
        if split["enough"]:
            assert split["summary"]["learners"] < summary["learners"]

    # The confusing question the demo plants is the one most got wrong first time.
    second = next(q for q in body["questions"] if q["number"] == 2)
    assert second["right_first_time"] < body["questions"][0]["right_first_time"]
