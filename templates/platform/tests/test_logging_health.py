import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.platform.health import health_router
from app.platform.logging import CorrelationIdMiddleware, JsonFormatter, correlation_id


def make_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/id")
    def current_id():  # a sync route: runs in a worker thread, the id must still be there
        return {"id": correlation_id.get()}

    return TestClient(app)


def test_request_id_is_kept_and_returned():
    response = make_client().get("/id", headers={"X-Request-ID": "req-abc.123"})
    assert response.json() == {"id": "req-abc.123"}
    assert response.headers["x-request-id"] == "req-abc.123"


def test_request_id_is_made_when_missing_or_unsafe():
    client = make_client()
    for headers in ({}, {"X-Request-ID": "bad id\nwith newline"}, {"X-Request-ID": "x" * 200}):
        response = client.get("/id", headers=headers)
        made = response.json()["id"]
        assert made and len(made) == 32 and response.headers["x-request-id"] == made


def test_json_log_lines_carry_service_and_request_id():
    token = correlation_id.set("req-1")
    try:
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello %s", ("you",), None)
        line = json.loads(JsonFormatter().format(record))
    finally:
        correlation_id.reset(token)
    assert line["message"] == "hello you"
    assert line["request_id"] == "req-1"
    assert line["service"] == "platformtest"
    assert line["level"] == "INFO"


def test_health():
    good = sessionmaker(bind=create_engine("sqlite://"))
    bad = sessionmaker(bind=create_engine("postgresql+psycopg://x:y@127.0.0.1:1/none"))
    for factory, status, body in [(good, 200, "ok"), (bad, 503, "unavailable")]:
        app = FastAPI()
        app.include_router(health_router(factory))
        client = TestClient(app)
        assert client.get("/health/live").json() == {"status": "ok"}
        response = client.get("/health/ready")
        assert response.status_code == status
        assert response.json() == {"status": body}


def test_install_platform_wires_everything():
    from app.platform.errors import Problem
    from app.platform.lifespan import install_platform

    app = FastAPI()
    install_platform(app, sessionmaker(bind=create_engine("sqlite://")))

    @app.get("/boom")
    def boom():
        raise Problem("nope", "No.", 409)

    client = TestClient(app)
    response = client.get("/boom", headers={"X-Request-ID": "r-1"})
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "nope", "message": "No."}}
    assert response.headers["x-request-id"] == "r-1"
    assert client.get("/health/ready").json() == {"status": "ok"}


def test_configure_logging_reads_log_level(monkeypatch):
    from app.platform.logging import configure_logging

    root = logging.getLogger()
    before = (root.level, root.handlers[:])
    try:
        monkeypatch.setenv("LOG_LEVEL", "warning")
        configure_logging()
        assert root.level == logging.WARNING
        configure_logging("debug")  # an explicit level wins
        assert root.level == logging.DEBUG
        monkeypatch.delenv("LOG_LEVEL")
        configure_logging()
        assert root.level == logging.INFO
    finally:
        root.setLevel(before[0])
        root.handlers[:] = before[1]


def test_unhandled_error_is_logged_and_answered_with_the_request_id(caplog):
    from app.platform.lifespan import install_platform

    app = FastAPI()
    install_platform(app, sessionmaker(bind=create_engine("sqlite://")))
    seen = []

    @app.get("/crash")
    def crash():
        raise RuntimeError("kaboom")

    class Capture(logging.Handler):
        def emit(self, record):
            seen.append((record.name, correlation_id.get(), record.exc_info))

    capture = Capture()
    logging.getLogger("sgjio.errors").addHandler(capture)
    try:
        response = TestClient(app).get("/crash", headers={"X-Request-ID": "req-boom"})
    finally:
        logging.getLogger("sgjio.errors").removeHandler(capture)
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers["x-request-id"] == "req-boom"
    assert [(name, rid) for name, rid, _ in seen] == [("sgjio.errors", "req-boom")]
    assert seen[0][2] is not None  # the traceback is in the log line
