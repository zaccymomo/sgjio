"""AI-generated lessons end to end (docs/ai-lessons-plan.md, docs/ai-lessons-api.md).

Runs against the stack with the generation worker's fake model (GENERATION_FAKE=true, the
default), so every figure is exact and nothing leaves the machine. The fake refuses any
request whose text contains "essay" (services/generation/README.md), which is how the
off-topic path is reached.
"""

import os

import httpx

from conftest import create_lesson, create_topic, eventually, progress, publish, unique
from shapes import check, problem

# Seconds to wait for a lesson: the fake model takes ~1 s; the real one up to ~1 min.
WAIT = float(os.environ.get("E2E_GENERATION_WAIT", "60"))
PENDING = {"requested", "writing", "checking"}


def options(http: httpx.Client) -> dict:
    response = http.get("/api/generate/options")
    assert response.status_code == 200, response.text
    return response.json()


def wait_for(http: httpx.Client, request_id: str) -> dict:
    """Poll a learner's request until it is no longer waiting."""

    def done():
        response = http.get(f"/api/generate/{request_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        return body if body["status"] not in PENDING else None

    return eventually(done, f"generated lesson {request_id} to finish", timeout=WAIT)


def published_topic(admin: httpx.Client, scratch_topics: list[str]) -> dict:
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    publish(admin, create_lesson(admin, topic["id"], questions=2, words=unique("kopi")))
    return topic


def answer_wrongly(http: httpx.Client, topic_id: str) -> None:
    """Take the topic's lesson choosing the wrong option, so both questions become mistakes."""

    def first_lesson():
        lessons = http.get(f"/api/topics/{topic_id}").json().get("lessons", [])
        return lessons[0]["id"] if lessons else None

    lesson_id = eventually(first_lesson, "the topic's lesson to reach Learning")
    lesson = http.get(f"/api/lessons/{lesson_id}").json()
    attempt = http.post(f"/api/lessons/{lesson_id}/attempts", json={"version": lesson["version"]})
    assert attempt.status_code == 201, attempt.text
    for card in lesson["cards"]:
        if card["question"]:
            wrong = next(o["id"] for o in card["question"]["options"] if o["id"].endswith("-wrong"))
            http.post(
                f"/api/attempts/{attempt.json()['id']}/answers",
                json={"question_id": card["question"]["id"], "option_id": wrong},
            )
    assert http.post(f"/api/attempts/{attempt.json()['id']}/finish").status_code == 200


def test_learner_generates_from_mistakes_and_plays(admin, scratch_topics, new_learner):
    topic = published_topic(admin, scratch_topics)
    learner = new_learner()
    http = learner.http
    answer_wrongly(http, topic["id"])

    choices = eventually(
        lambda: (o := options(http))
        and next((t for t in o["topics"] if t["id"] == topic["id"] and t["mistakes"] == 2), None)
        and o,
        "options to list our topic with its 2 mistakes",
    )
    assert choices["has_generated"] is False
    left = choices["left_today"]
    before = progress(http)
    review_before = check(http.get("/api/review"), "GET /api/review", 200)

    response = http.post(
        "/api/generate",
        json={
            "topic_id": topic["id"],
            "focus": "mistakes",
            "ask": "My colleagues keep asking can or not",
            "difficulty": "right",
            "length": "short",
        },
    )
    assert response.status_code == 202, response.text
    request = response.json()
    assert request["status"] in PENDING and request["left_today"] == left - 1

    ready = wait_for(http, request["id"])
    assert ready["status"] == "ready", ready
    assert ready["lesson"]["cards"] == 4 and ready["lesson"]["questions"] == 1
    assert ready["covers"] and all(c["lesson_title"] for c in ready["covers"])
    assert ready["ask"] == "My colleagues keep asking can or not"

    listed = http.get("/api/generated").json()
    assert listed[0]["id"] == request["id"] and listed[0]["title"] == ready["lesson"]["title"]

    # The deck never says which option is right, and answers are checked on the server.
    deck = http.get(f"/api/generated/{request['id']}/lesson").json()
    assert len(deck["cards"]) == 4 and deck["assets"] == {}
    assert "correct" not in str([c["question"] for c in deck["cards"] if c["question"]])
    attempt = http.post(f"/api/generated/{request['id']}/attempts")
    assert attempt.status_code in (200, 201), attempt.text
    for card in deck["cards"]:
        if card["question"]:
            checked = http.post(
                f"/api/generated/attempts/{attempt.json()['id']}/answers",
                json={
                    "question_id": card["question"]["id"],
                    "option_id": card["question"]["options"][0]["id"],
                },
            )
            assert checked.status_code == 200, checked.text
            assert set(checked.json()) >= {"correct", "correct_option_id", "explanation", "why_not"}
    finished = http.post(f"/api/generated/attempts/{attempt.json()['id']}/finish")
    assert finished.status_code == 200, finished.text
    assert finished.json()["best"]["scored"] == 1

    rated = http.post(
        f"/api/generated/{request['id']}/rating", json={"useful": False, "reasons": ["too_easy"]}
    )
    assert rated.status_code == 204, rated.text
    card_id = deck["cards"][0]["id"]
    flagged = http.post(
        f"/api/generated/{request['id']}/reports",
        json={"card_id": card_id, "reason": "wrong", "note": "e2e"},
    )
    assert flagged.status_code == 201, flagged.text

    # Nothing generated counts: the circles, totals and mistakes are exactly as before.
    after = progress(http)
    assert (after["completed"], after["available"]) == (before["completed"], before["available"])
    assert check(http.get("/api/review"), "GET /api/review", 200) == review_before
    assert options(http)["has_generated"] is True


def test_off_topic_request_is_refused_without_using_a_slot(admin, scratch_topics, new_learner):
    topic = published_topic(admin, scratch_topics)
    http = new_learner().http
    eventually(
        lambda: any(t["id"] == topic["id"] for t in options(http)["topics"]),
        "our topic in the options",
    )
    left = options(http)["left_today"]

    response = http.post(
        "/api/generate",
        json={
            "topic_id": topic["id"],
            "focus": "new",
            "ask": "Write my PR application essay",
            "difficulty": "right",
            "length": "usual",
        },
    )
    assert response.status_code == 202, response.text
    failed = wait_for(http, response.json()["id"])
    assert failed["status"] == "failed" and failed["failure"]["code"] == "off_topic"
    assert "everyday life in Singapore" in failed["failure"]["message"]
    assert options(http)["left_today"] == left
    assert all(item["id"] != response.json()["id"] for item in http.get("/api/generated").json())


def test_my_mistakes_needs_mistakes(admin, scratch_topics, new_learner):
    topic = published_topic(admin, scratch_topics)
    http = new_learner().http
    eventually(
        lambda: any(t["id"] == topic["id"] for t in options(http)["topics"]),
        "our topic in the options",
    )
    response = http.post(
        "/api/generate",
        json={
            "topic_id": topic["id"],
            "focus": "mistakes",
            "ask": None,
            "difficulty": "right",
            "length": "short",
        },
    )
    problem(response, 409, "no_mistakes")


def test_admin_draft_must_be_reviewed_before_publishing(admin, scratch_topics, new_learner):
    topic = published_topic(admin, scratch_topics)
    response = admin.post(
        "/api/admin/lessons/generate",
        json={
            "topic_id": topic["id"],
            "level": 1,
            "notes": "Say 'can' to agree quickly. 'Cannot lah' is a friendly no.",
            "cards": 4,
        },
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]

    def done():
        body = admin.get(f"/api/admin/generation/{job_id}").json()
        return body if body["status"] in ("done", "failed") else None

    job = eventually(done, "the admin's draft", timeout=WAIT)
    assert job["status"] == "done" and job["lesson_id"], job

    draft = admin.get(f"/api/admin/lessons/{job['lesson_id']}").json()
    assert draft["origin"] == "ai" and draft["ai_reviewed_at"] is None
    assert draft["topic_id"] == topic["id"] and draft["level"] == 1

    refused = admin.post(
        f"/api/admin/lessons/{draft['id']}/publish", json={"updated_at": draft["updated_at"]}
    )
    problem(refused, 409, "review_required")
    published = admin.post(
        f"/api/admin/lessons/{draft['id']}/publish",
        json={"updated_at": draft["updated_at"], "reviewed": True},
    )
    assert published.status_code == 200, published.text
    assert published.json()["ai_reviewed_at"] is not None

    # Once published it is an ordinary lesson that learners can open.
    http = new_learner().http
    eventually(
        lambda: http.get(f"/api/lessons/{draft['id']}").status_code == 200,
        "the published AI draft to reach learners",
    )
