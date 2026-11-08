"""Identity's command-line tools (detailed-plan 7.2): create-admin, send-reset, the demo
learners, republish-learners and health. Each change is announced with its event."""

import uuid

import pytest
from sqlalchemy import func, select

from app import cli
from app.demo import DOMAIN
from app.models import User, UserRole, UserType
from app.seed import seed
from tests.helpers import emails, outbox_events


def _demo_ids(nonce: str, count: int) -> set[uuid.UUID]:
    return {
        uuid.uuid5(uuid.NAMESPACE_URL, f"sgjio:user:learner{n:02}@{DOMAIN}:{nonce}")
        for n in range(1, count + 1)
    }


def _demo_learners(db) -> list[User]:
    return list(db.scalars(select(User).where(User.email.like(f"%@{DOMAIN}"))))


# --- create-admin ---------------------------------------------------------------------------


def test_create_admin_registers_a_new_administrator(db, capsys):
    email = "new@sgjio.example.com"
    assert cli.main(["create-admin", "--email", email, "--password", "AdminPass123"]) == 0
    admin = db.scalar(select(User).where(User.email == email))
    [event] = outbox_events("identity.user.registered")
    assert event["data"]["user_id"] == str(admin.id)
    assert event["data"]["role"] == "admin"
    assert event["data"]["user_type"] is None
    assert "Created administrator" in capsys.readouterr().out


def test_create_admin_for_an_existing_administrator_registers_nothing_new(db, make_user):
    make_user("old@sgjio.example.com", role=UserRole.ADMIN)
    assert (
        cli.main(["create-admin", "--email", "old@sgjio.example.com", "--password", "Again12345"])
        == 0
    )
    assert outbox_events() == []


def test_create_admin_refuses_a_weak_password(db):
    assert cli.main(["create-admin", "--email", "a@sgjio.example.com", "--password", "weak"]) == 1
    assert db.scalar(select(User)) is None
    assert outbox_events() == []


# --- send-reset -----------------------------------------------------------------------------


def test_send_reset_queues_the_email(make_user, capsys):
    make_user(role=UserRole.ADMIN)
    assert cli.main(["send-reset", "--email", "user@example.com", "--scope", "admin"]) == 0
    [email] = emails()
    assert email["data"]["audience"] == "admin"
    assert "http://localhost:8025" in capsys.readouterr().out


# --- Demo learners --------------------------------------------------------------------------


def test_seed_demo_learners_adds_newcomers_and_singaporeans_with_the_runs_ids(db, capsys):
    assert cli.main(["seed-demo-learners", "--count", "6", "--run-nonce", "run1"]) == 0
    learners = _demo_learners(db)
    assert {learner.id for learner in learners} == _demo_ids("run1", 6)
    types = sorted(learner.user_type.value for learner in learners)
    assert types == ["newcomer"] * 4 + ["singaporean"] * 2
    assert all(learner.intro_finished_at for learner in learners)
    registered = outbox_events("identity.user.registered")
    assert {uuid.UUID(e["data"]["user_id"]) for e in registered} == _demo_ids("run1", 6)
    assert "run nonce: run1" in capsys.readouterr().out


def test_the_default_is_sixty_learners_forty_of_them_newcomers(db):
    assert cli.main(["seed-demo-learners"]) == 0
    learners = _demo_learners(db)
    assert len(learners) == 60
    assert sum(learner.user_type == UserType.NEWCOMER for learner in learners) == 40


def test_demo_learners_can_never_sign_in(client, db):
    cli.main(["seed-demo-learners", "--count", "1", "--run-nonce", "x"])
    for password in ["UserPass123", "Password123", ""]:
        response = client.post(
            "/api/auth/sign-in", json={"email": f"learner01@{DOMAIN}", "password": password or "x"}
        )
        assert response.status_code == 401


def test_a_new_run_replaces_the_demo_learners_with_fresh_ids(db):
    cli.main(["seed-demo-learners", "--count", "3", "--run-nonce", "first"])
    cli.main(["seed-demo-learners", "--count", "3", "--run-nonce", "second"])

    assert {learner.id for learner in _demo_learners(db)} == _demo_ids("second", 3)
    deleted = outbox_events("identity.user.deleted")
    assert {uuid.UUID(e["data"]["user_id"]) for e in deleted} == _demo_ids("first", 3)
    assert all(e["aggregate_version"] == 2 for e in deleted)


def test_clear_demo_learners_deletes_only_them(db, make_user):
    make_user("real@example.com")
    cli.main(["seed-demo-learners", "--count", "2", "--run-nonce", "n"])
    assert cli.main(["clear-demo-learners"]) == 0
    assert _demo_learners(db) == []
    assert [user.email for user in db.scalars(select(User))] == ["real@example.com"]
    deleted = outbox_events("identity.user.deleted")
    assert {uuid.UUID(e["data"]["user_id"]) for e in deleted} == _demo_ids("n", 2)
    # Nothing left to clear: no further events.
    assert cli.main(["clear-demo-learners"]) == 0
    assert len(outbox_events("identity.user.deleted")) == 2


def test_seed_demo_learners_refuses_a_count_below_one(db):
    assert cli.main(["seed-demo-learners", "--count", "0"]) == 1
    assert outbox_events() == []


# --- republish-learners ---------------------------------------------------------------------


def test_republish_learners_registers_every_account_again(db):
    seed(db)
    first = outbox_events("identity.user.registered")
    assert cli.main(["republish-learners"]) == 0
    again = outbox_events("identity.user.registered")[len(first) :]
    assert len(again) == db.scalar(select(func.count()).select_from(User))
    assert sorted(e["data"]["user_id"] for e in again) == sorted(
        e["data"]["user_id"] for e in first
    )
    # The same facts as the first time, under new event ids.
    by_user = {e["data"]["user_id"]: e["data"] for e in first}
    assert all(e["data"] == by_user[e["data"]["user_id"]] for e in again)
    assert not {e["event_id"] for e in again} & {e["event_id"] for e in first}


# --- seed and health ------------------------------------------------------------------------


def test_seed_command(db, capsys):
    assert cli.main(["seed"]) == 0
    assert "Created:" in capsys.readouterr().out
    assert cli.main(["seed"]) == 0
    assert "Nothing to do" in capsys.readouterr().out


@pytest.mark.integration
def test_health_checks_the_database_and_the_broker(capsys):
    from app.platform.broker import close_quietly, connect

    try:
        close_quietly(connect("test"))
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"RabbitMQ is not running ({error})")
    assert cli.main(["health"]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_health_fails_without_a_broker(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise ConnectionError("refused")

    monkeypatch.setattr(cli, "connect", refuse)
    assert cli.main(["health"]) == 1
