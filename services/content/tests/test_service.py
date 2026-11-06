"""The service's own edges: who may call it (the gateway's headers), health, and its
commands (docs/architecture/detailed-plan.md, section 7.2)."""

import uuid

import pytest

from app.cli import main as cli
from app.platform.principal import Principal
from app.platform.testing import admin_headers, app_headers, headers_for
from tests.conftest import outbox_events

NOT_SIGNED_IN = {"detail": {"code": "not_signed_in", "message": "Please sign in to continue."}}


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param(admin_headers(uuid.uuid4()) | {"X-Gateway-Key": "wrong"}, id="wrong key"),
        pytest.param(
            {k: v for k, v in admin_headers(uuid.uuid4()).items() if k != "X-Gateway-Key"},
            id="no key: did not come through the gateway",
        ),
        pytest.param(app_headers(uuid.uuid4()), id="app scope on an admin route"),
        pytest.param(
            headers_for(Principal(uuid.uuid4(), "admin", "user", None, False)),
            id="admin scope without the admin role",
        ),
        pytest.param(admin_headers(uuid.uuid4()) | {"X-User-Id": "nobody"}, id="bad user id"),
    ],
)
def test_admin_routes_need_the_gateways_admin_principal(client, headers):
    response = client.get("/api/admin/topics", headers=headers)
    assert (response.status_code, response.json()) == (401, NOT_SIGNED_IN)


def test_reports_need_an_app_principal(client):
    url = f"/api/lessons/{uuid.uuid4()}/reports"
    body = {"version": 1, "card_id": "c1", "reason": "wrong"}
    assert client.post(url, json=body, headers=admin_headers()).status_code == 401
    response = client.post(url, json=body, headers=app_headers())
    assert response.json()["detail"]["code"] == "lesson_unavailable"


def test_media_is_public_without_the_gateway(client):
    response = client.get(f"/api/media/{uuid.uuid4()}")
    assert response.json()["detail"]["code"] == "media_not_found"


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}


def test_every_response_carries_a_request_id(client):
    assert client.get("/health/live").headers["x-request-id"]
    assert (
        client.get("/health/live", headers={"X-Request-ID": "abc"}).headers["x-request-id"] == "abc"
    )


# --- Commands ---------------------------------------------------------------------------------


def test_cli_health_checks_database_and_broker(capsys):
    code = cli(["health"])
    out = capsys.readouterr().out
    assert "database: ok" in out
    if "broker: unavailable" in out:  # RabbitMQ is not running: only that fails
        assert code == 1
    else:
        assert code == 0


@pytest.mark.repeats_versions
def test_cli_seed_then_republish_catalog(capsys):
    assert cli(["seed"]) == 0
    seeded = len(outbox_events())
    assert cli(["seed"]) == 0
    assert "Nothing to do" in capsys.readouterr().out
    assert len(outbox_events()) == seeded

    assert cli(["republish-catalog"]) == 0

    assert "Republished 6 topic(s)" in capsys.readouterr().out
    assert len(outbox_events()) == 2 * seeded  # the same events once more


def test_cli_prune_media(capsys):
    assert cli(["prune-media"]) == 0
    assert "No unused files" in capsys.readouterr().out
