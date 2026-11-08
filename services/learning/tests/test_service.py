"""The service as a whole: its routes are the monolith's learning routes exactly, health
checks, the gateway key, errors and the command-line tools. New tests."""

import uuid

from sqlalchemy import func, select

from app import cli
from app.main import app
from app.models import ErasedLearner, LearnableTopic, Learner, LessonCompletion
from app.platform.testing import app_headers
from tests.support.records import complete

# Every learning route in api/app/routers (lessons, progress, review, aptitude, and the
# insights route from admin), method and path as the front ends call them.
MONOLITH_ROUTES = {
    ("GET", "/api/lessons/{lesson_id}"),
    ("POST", "/api/lessons/{lesson_id}/attempts"),
    ("POST", "/api/attempts/{attempt_id}/answers"),
    ("POST", "/api/attempts/{attempt_id}/finish"),
    ("GET", "/api/progress"),
    ("GET", "/api/topics/{topic_id}"),
    ("GET", "/api/search"),
    ("GET", "/api/review"),
    ("POST", "/api/aptitude/start"),
    ("POST", "/api/aptitude/next"),
    ("POST", "/api/aptitude/submit"),
    ("GET", "/api/aptitude/result"),
    ("GET", "/api/admin/lessons/{lesson_id}/insights"),
}


def test_the_routes_are_the_monoliths_learning_routes():
    routes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/")
        for method in operations
    }
    assert routes == MONOLITH_ROUTES


def test_every_api_route_refuses_a_request_without_the_gateway_key(client):
    ids = {"lesson_id": uuid.uuid4(), "attempt_id": uuid.uuid4(), "topic_id": uuid.uuid4()}
    for method, path in MONOLITH_ROUTES:
        url = path.format(**ids)
        headers = app_headers() | {"X-Gateway-Key": ""}
        response = client.request(method, url, headers=headers, json={})
        assert response.status_code == 401, (method, path)
        assert response.json() == {
            "detail": {"code": "not_signed_in", "message": "Please sign in to continue."}
        }


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}


def test_every_answer_carries_a_request_id(client):
    response = client.get("/api/progress", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_swagger_is_served_directly(client):
    assert client.get("/docs").status_code == 200
    assert "/api/progress" in client.get("/openapi.json").json()["paths"]


def test_cli_health(capsys):
    assert cli.main(["health"]) == 0
    assert "database: ok" in capsys.readouterr().out


def test_cli_seed_explains_what_is_missing(capsys):
    assert cli.main(["seed"]) == 1
    assert "wait-for-read-models" in capsys.readouterr().err


def test_cli_wait_times_out_with_what_is_missing(capsys):
    assert cli.main(["wait-for-read-models", "--timeout", "0"]) == 1
    assert "Timed out" in capsys.readouterr().out


def test_reset_and_republish_rebuilds_the_read_models(
    client, db, bus, content, identity, make_user
):
    """detailed-plan 3.2: reset, then the producers republish, through the consumer."""
    from tests.conftest import sign_in

    user = make_user()
    gone = make_user("gone@example.com")
    identity.delete(gone)
    topic = content.topic("Singlish")
    lesson = content.lesson(topic, "Lah")
    complete(db, user, lesson)
    sign_in(client, user)
    before = client.get("/api/progress").json()

    assert cli.main(["reset-read-models", "--yes"]) == 0
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(LearnableTopic)) == 0
    assert client.get("/api/progress").json()["available"] == 0
    # Learners' own data and the erasure tombstones survive a reset.
    assert db.scalar(select(func.count()).select_from(LessonCompletion)) == 1
    assert db.scalar(select(func.count()).select_from(ErasedLearner)) == 1

    # Republishing (republish-catalog, republish-learners) sends every aggregate's current
    # state again: here, the latest events Content and Identity sent for each.
    latest: dict[str, dict] = {}
    for envelope in bus.sent:
        latest[(envelope["type"], envelope["aggregate_id"])] = envelope
    for envelope in latest.values():
        bus.deliver(envelope)

    assert client.get("/api/progress").json() == before
    db.expire_all()
    assert db.get(Learner, gone.id) is None  # an erased learner is not brought back
