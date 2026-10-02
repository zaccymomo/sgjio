"""Migration 0004 numbers existing topics and lessons (SCRUM-66).

Runs the real migration over rows inserted at revision 0003, so the backfill is tested the
way it runs on a real database, not through the models.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db import engine

API_DIR = Path(__file__).resolve().parent.parent

EARLY = "2026-01-01 00:00:00+00"
LATE = "2026-02-01 00:00:00+00"


def _config() -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    return config


def _insert_rows_at_0003() -> None:
    with engine.begin() as conn:
        topic = text(
            "INSERT INTO topics (id, name, archived_at, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :name, :archived, :created, :created)"
        )
        conn.execute(topic, {"name": "Workplace", "archived": None, "created": LATE})
        # Created together, as the seed does: the name decides.
        conn.execute(topic, {"name": "Singlish", "archived": None, "created": EARLY})
        conn.execute(topic, {"name": "Festivals", "archived": EARLY, "created": EARLY})

        lesson = text(
            "INSERT INTO lessons (id, title, content, topic_id, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :title, '', "
            "(SELECT id FROM topics WHERE name = :topic), :status, :created, :created)"
        )
        for title, topic_name, status, created in [
            ("Zebra crossings", "Singlish", "published", EARLY),
            ("Already", "Singlish", "draft", LATE),
            ("Lah", "Singlish", "withdrawn", EARLY),
            ("Lunch", "Workplace", "published", EARLY),
            ("Loose draft B", None, "draft", EARLY),
            ("Loose draft A", None, "draft", EARLY),
            ("Earlier loose draft", None, "draft", "2025-12-01 00:00:00+00"),
        ]:
            conn.execute(
                lesson, {"title": title, "topic": topic_name, "status": status, "created": created}
            )


def test_backfill_numbers_topics_and_lessons_in_creation_order():
    config = _config()
    command.downgrade(config, "0003")
    try:
        _insert_rows_at_0003()
        command.upgrade(config, "0004")
    finally:
        command.upgrade(config, "head")

    with engine.connect() as conn:
        topics = conn.execute(text("SELECT name, position FROM topics ORDER BY position")).all()
        lessons = conn.execute(
            text(
                "SELECT t.name, l.title, l.position FROM lessons l "
                "LEFT JOIN topics t ON t.id = l.topic_id ORDER BY t.name NULLS LAST, l.position"
            )
        ).all()

    # Archived topics are numbered too, in the same sequence.
    assert [tuple(row) for row in topics] == [("Festivals", 0), ("Singlish", 1), ("Workplace", 2)]
    assert [tuple(row) for row in lessons] == [
        # Per topic, by creation then title; status does not matter.
        ("Singlish", "Lah", 0),
        ("Singlish", "Zebra crossings", 1),
        ("Singlish", "Already", 2),
        ("Workplace", "Lunch", 0),
        # Lessons with no topic are numbered as one group of their own.
        (None, "Earlier loose draft", 0),
        (None, "Loose draft A", 1),
        (None, "Loose draft B", 2),
    ]
