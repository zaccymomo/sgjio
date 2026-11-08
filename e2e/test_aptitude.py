"""The aptitude question bank (admin) and the aptitude test (learner), across Content and
Learning (detailed plan 8.3 item 12).

The bank is shared by everyone, so the admin test only ever adds questions to its own
topics and archives them at the end (an archived topic leaves the bank), whatever happens.
"""

import httpx

from conftest import create_topic, eventually, progress, unique
from shapes import check, problem

BANK = "GET /api/admin/aptitude-questions"


def _question(topic_id: str, level: int, **extra) -> dict:
    return {
        "topic_id": topic_id,
        "level": level,
        "prompt": f"{unique('Prompt')} at level {level}?",
        "options": [
            {"id": "yes", "text": "Yes", "correct": True},
            {"id": "no", "text": "No"},
        ],
        **extra,
    }


def _readiness(admin: httpx.Client, topic_id: str) -> dict | None:
    bank = check(admin.get("/api/admin/aptitude-questions"), BANK, 200)
    return next((t for t in bank["topics"] if t["topic_id"] == topic_id), None)


def test_question_bank_readiness_and_topic_rules(admin, scratch_topics, new_learner):
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    assert _readiness(admin, topic["id"]) is None

    created = check(
        admin.post("/api/admin/aptitude-questions", json=_question(topic["id"], 1)),
        "POST /api/admin/aptitude-questions",
        201,
    )
    assert created["correct_option_id"] == "yes" and created["topic_name"] == topic["name"]
    bank = check(admin.get("/api/admin/aptitude-questions"), BANK, 200)
    assert bank["ready"] is False
    ours = _readiness(admin, topic["id"])
    assert ours["ready"] is False
    assert ours["counts_by_level"] == {"1": 1, "2": 0, "3": 0, "4": 0, "5": 0}

    edited = check(
        admin.patch(
            f"/api/admin/aptitude-questions/{created['id']}",
            json={
                "prompt": "Edited prompt?",
                "options": [
                    {"id": "a", "text": "A"},
                    {"id": "b", "text": "B", "correct": True},
                    {"id": "c", "text": "C"},
                ],
            },
        ),
        "PATCH /api/admin/aptitude-questions/{question_id}",
        200,
    )
    assert edited["prompt"] == "Edited prompt?" and edited["correct_option_id"] == "b"
    assert edited["level"] == 1
    refused = admin.patch(f"/api/admin/aptitude-questions/{created['id']}", json={"level": 2})
    assert refused.status_code == 422, refused.text
    problem(
        admin.post(
            "/api/admin/aptitude-questions",
            json=_question(
                topic["id"], 2, options=[{"id": "x", "text": "X"}, {"id": "y", "text": "Y"}]
            ),
        ),
        422,
        "one_correct_required",
    )

    for level in range(2, 6):
        check(
            admin.post("/api/admin/aptitude-questions", json=_question(topic["id"], level)),
            "POST /api/admin/aptitude-questions",
            201,
        )
    assert _readiness(admin, topic["id"])["ready"] is True

    # 8.3.12: a topic that ever had a question can't be deleted, even once it is empty.
    other = create_topic(admin)
    scratch_topics.append(other["id"])
    moving = check(
        admin.post("/api/admin/aptitude-questions", json=_question(other["id"], 3)),
        "POST /api/admin/aptitude-questions",
        201,
    )
    check(
        admin.patch(
            f"/api/admin/aptitude-questions/{moving['id']}", json={"topic_id": topic["id"]}
        ),
        "PATCH /api/admin/aptitude-questions/{question_id}",
        200,
    )
    # With no question left it leaves the bank (only topics with a question are assessed).
    assert _readiness(admin, other["id"]) is None
    problem(admin.delete(f"/api/admin/topics/{other['id']}"), 409, "topic_not_empty")

    # Learning's copy of the bank follows: the learner's test covers every topic in it.
    learner = new_learner()

    def quiz_matches_bank() -> bool:
        topics = check(admin.get("/api/admin/aptitude-questions"), BANK, 200)["topics"]
        response = learner.http.post("/api/aptitude/start")
        if response.status_code != 200:
            return False
        step = check(response, "POST /api/aptitude/start", 200)
        return step["question"]["topic_count"] == len(topics)

    assert _readiness(admin, topic["id"])["ready"] is True
    eventually(quiz_matches_bank, "the learner's test to include our topic")

    # Archiving our two topics takes them out of the bank again.
    for topic_id in (topic["id"], other["id"]):
        admin.post(f"/api/admin/topics/{topic_id}/archive")
    assert _readiness(admin, topic["id"]) is None
    bank = check(admin.get("/api/admin/aptitude-questions"), BANK, 200)
    assert bank["ready"] is True, [t for t in bank["topics"] if not t["ready"]]
    eventually(quiz_matches_bank, "the learner's test to drop our topic")


def _correct_answers(admin: httpx.Client) -> dict[str, str]:
    bank = check(admin.get("/api/admin/aptitude-questions"), BANK, 200)
    return {question["id"]: question["correct_option_id"] for question in bank["questions"]}


def test_learner_takes_the_aptitude_test(admin, new_learner):
    """Right answers in the first topic (placed at Level 5, every lesson exempted), wrong in
    the rest (Level 0)."""
    learner = new_learner()
    http = learner.http
    correct = _correct_answers(admin)

    # Another test may have just changed the bank; Learning's copy follows within moments.
    started = eventually(
        lambda: (r := http.post("/api/aptitude/start")).status_code == 200 and r,
        "the aptitude test to be ready",
    )
    step = check(started, "POST /api/aptitude/start", 200)
    first_topic = step["question"]["topic_id"]
    topic_count = step["question"]["topic_count"]
    answers: list[dict] = []
    while not step["done"]:
        question = step["question"]
        assert question["options"][-1] == {"id": "not-sure", "text": "I’m not sure"}
        if question["topic_id"] == first_topic:
            option = correct[question["id"]]
        else:
            option = next(
                o["id"] for o in question["options"] if o["id"] != correct[question["id"]]
            )
        answers.append({"question_id": question["id"], "option_id": option})
        step = check(
            http.post("/api/aptitude/next", json={"answers": answers}),
            "POST /api/aptitude/next",
            200,
        )
    assert step["question"] is None
    assert len(answers) == 5 + (topic_count - 1)

    result = check(
        http.post("/api/aptitude/submit", json={"answers": answers}),
        "POST /api/aptitude/submit",
        200,
    )
    assert result["correct"] == 5 and result["total"] == len(answers)
    placements = {p["topic_id"]: p for p in result["placements"]}
    assert placements[first_topic]["level"] == 5
    assert placements[first_topic]["exempted"] == placements[first_topic]["available"] > 0
    assert all(
        p["level"] == 0 and p["exempted"] == 0 for t, p in placements.items() if t != first_topic
    )
    # Each placement lists the lessons it exempts, lowest level first; none where it is 0.
    listed = placements[first_topic]["lessons"]
    assert len(listed) == placements[first_topic]["exempted"]
    assert [row["level"] for row in listed] == sorted(row["level"] for row in listed)
    assert all(p["lessons"] == [] for t, p in placements.items() if t != first_topic)

    assert check(http.get("/api/aptitude/result"), "GET /api/aptitude/result", 200) == result
    # Taken once only.
    problem(http.post("/api/aptitude/start"), 409, "quiz_already_completed")

    home = progress(http)
    assert home["aptitude_taken"] is True
    circle = next(t for t in home["topics"] if t["id"] == first_topic)
    assert circle["exempted"] == circle["available"] and circle["level"] == 5
    page = check(http.get(f"/api/topics/{first_topic}"), "GET /api/topics/{topic_id}", 200)
    assert all(lesson["exempted"] for lesson in page["lessons"])
    # The suggestion skips exempted lessons.
    if home["suggestion"]:
        assert home["suggestion"]["topic_id"] != first_topic


def test_skipping_the_aptitude_test_stores_nothing(new_learner):
    """SCRUM-98: "Skip for now" only leaves the page; there is no skip call any more."""
    learner = new_learner()
    response = learner.http.post("/api/aptitude/skip")
    assert response.status_code == 404, response.text
    assert progress(learner.http)["aptitude_taken"] is False
    problem(learner.http.get("/api/aptitude/result"), 404, "attempt_not_found")


def test_aptitude_does_not_need_a_profile(new_learner):
    """Profile setup can be skipped too, so the test starts without one."""
    learner = new_learner(onboarded=False)
    check(learner.http.post("/api/aptitude/start"), "POST /api/aptitude/start", 200)


def test_aptitude_is_for_newcomers(new_learner):
    learner = new_learner(user_type="singaporean")
    problem(learner.http.post("/api/aptitude/start"), 403, "quiz_for_newcomers")
