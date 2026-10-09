"""Migration 0007 turns each right-or-wrong completion into a score (SCRUM-16).

Runs the real migration over rows inserted at revision 0006."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db import engine

API_DIR = Path(__file__).resolve().parent.parent


def _config() -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    return config


def test_completions_become_one_of_one_or_none_of_one():
    config = _config()
    command.downgrade(config, "0006")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, name, email, password_hash, role) VALUES "
                    "(gen_random_uuid(), 'U', 'u@example.com', 'x', 'user')"
                )
            )
            conn.execute(
                text("INSERT INTO topics (id, name, position) VALUES (gen_random_uuid(), 'T', 0)")
            )
            for title, correct in [("Right", True), ("Wrong", False)]:
                conn.execute(
                    text(
                        "WITH l AS (INSERT INTO lessons "
                        "(id, title, topic_id, status, position, draft) "
                        "VALUES (gen_random_uuid(), :title, (SELECT id FROM topics), "
                        "'published', 0, '{\"cards\": []}') RETURNING id) "
                        "INSERT INTO lesson_completions "
                        "(id, user_id, lesson_id, answered_correctly) "
                        "SELECT gen_random_uuid(), (SELECT id FROM users), l.id, :correct FROM l"
                    ),
                    {"title": title, "correct": correct},
                )

        command.upgrade(config, "0007")

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT l.title, c.best_correct, c.best_scored, c.best_attempt_id "
                    "FROM lesson_completions c JOIN lessons l ON l.id = c.lesson_id "
                    "ORDER BY l.title"
                )
            ).all()
        assert [tuple(row) for row in rows] == [("Right", 1, 1, None), ("Wrong", 0, 1, None)]
    finally:
        command.upgrade(config, "head")
