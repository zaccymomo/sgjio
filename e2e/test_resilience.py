"""Resilience drills (detailed plan 8.3, "Resilience drills"): stop one container at a time
and check the declared degradation, then that it recovers. They stop and start containers
of the sgjio-ms compose project, so they only run when asked:

    E2E_RESILIENCE=1 e2e/.venv/bin/python -m pytest e2e -m resilience

(scripts/e2e.sh --resilience does the same.)
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

from conftest import (
    client,
    create_lesson,
    create_topic,
    eventually,
    learner_sees,
    publish,
)
from shapes import check, not_signed_in

pytestmark = [
    pytest.mark.resilience,
    pytest.mark.skipif(
        os.environ.get("E2E_RESILIENCE") != "1", reason="set E2E_RESILIENCE=1 to stop containers"
    ),
]

ROOT = Path(__file__).resolve().parents[1]
UNAVAILABLE = {
    "detail": {
        "code": "service_unavailable",
        "message": "SGJio is unavailable right now. Please try again in a moment.",
    }
}


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, capture_output=True)


def test_learning_down_then_catches_up(admin, scratch_topics, new_learner):
    learner = new_learner()
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    compose("stop", "learning")
    try:
        response = learner.http.get("/api/progress")
        assert (response.status_code, response.json()) == (503, UNAVAILABLE)
        assert response.headers["retry-after"] == "5"
        # Identity and Content keep working; authoring goes on.
        check(learner.http.get("/api/auth/me"), "GET /api/auth/me", 200)
        lesson = publish(admin, create_lesson(admin, topic["id"]))
    finally:
        compose("up", "-d", "--wait", "learning")
    # The publish waited on the broker and arrives once Learning is back.
    eventually(lambda: learner.http.get("/api/progress").status_code == 200, "Learning to answer")
    eventually(lambda: learner_sees(learner.http, lesson["id"]), "the lesson published meanwhile")


def test_identity_down_refuses_signed_in_routes_but_serves_media(admin, new_learner):
    learner = new_learner()
    lessons = check(admin.get("/api/admin/lessons"), "GET /api/admin/lessons", 200)
    cover = next(lesson["cover_asset_id"] for lesson in lessons if lesson["cover_asset_id"])
    compose("stop", "identity")
    try:
        for response in (
            learner.http.get("/api/progress"),
            learner.http.get("/api/auth/me"),
            admin.get("/api/admin/topics"),
        ):
            assert (response.status_code, response.json()) == (503, UNAVAILABLE)
        with client() as anonymous:
            assert anonymous.get(f"/api/media/{cover}").status_code == 200
            assert anonymous.get("/api/health").status_code == 200
            # No session cookie at all is signed out for certain: the gateway says so
            # without Identity, so a visitor still gets the sign-in page.
            not_signed_in(anonymous.get("/api/progress"))
            not_signed_in(anonymous.get("/api/admin/topics"))
    finally:
        compose("up", "-d", "--wait", "identity")
    eventually(lambda: learner.http.get("/api/progress").status_code == 200, "Identity to answer")


def test_learning_database_down_answers_503_not_500(new_learner):
    """A service whose own database is down says "try again in a moment", as when the whole
    service is down, instead of a bare 500; it recovers by itself when Postgres is back."""
    learner = new_learner()
    compose("stop", "learning-db")
    try:
        response = learner.http.get("/api/progress")
        assert (response.status_code, response.json()) == (503, UNAVAILABLE)
        assert response.headers["retry-after"] == "5"
        assert response.headers["x-request-id"]
        # Other services are untouched.
        check(learner.http.get("/api/auth/me"), "GET /api/auth/me", 200)
    finally:
        compose("up", "-d", "--wait", "learning-db")
    eventually(lambda: learner.http.get("/api/progress").status_code == 200, "Learning's database")


def test_broker_outage_delays_but_never_loses_a_publish(admin, scratch_topics, new_learner):
    """With RabbitMQ down, publishing still succeeds (the outbox keeps the event); once the
    broker is back the relay and consumers reconnect within seconds (backoff is capped at
    5 s however long the outage was) and the learner sees the lesson."""
    learner = new_learner()
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    compose("stop", "rabbitmq")
    try:
        time.sleep(20)  # long enough for every reconnect backoff to reach its cap
        lesson = publish(admin, create_lesson(admin, topic["id"]))
        assert learner_sees(learner.http, lesson["id"]) is None
    finally:
        compose("up", "-d", "--wait", "rabbitmq")
    eventually(lambda: learner_sees(learner.http, lesson["id"]), "the lesson published meanwhile")
