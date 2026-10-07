"""Migration 0005 turns lessons into decks of cards with versions (SCRUM-19, SCRUM-52).

Runs the real migration over rows inserted at revision 0004, so the conversion is tested the
way it runs on a real database, not through the models.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db import engine
from app.lesson_doc import LessonDoc

API_DIR = Path(__file__).resolve().parent.parent

ARTICLE = (
    "## Chope first, then order\n\n"
    "People reserve a seat with a packet of tissues.\n\n"
    "## Kopi lingo\n\n"
    "- **Kopi**: coffee with condensed milk\n"
    "- **Kopi O**: black coffee with sugar"
)


def _config() -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    return config


def _insert_rows_at_0004() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO topics (id, name, position) VALUES (gen_random_uuid(), 'Hawker', 0)")
        )
        lesson = text(
            "INSERT INTO lessons (id, title, content, topic_id, status, published_at, position) "
            "VALUES (gen_random_uuid(), :title, :content, (SELECT id FROM topics), :status, "
            ":published_at, 0) RETURNING id"
        )
        published = conn.execute(
            lesson,
            {
                "title": "Published",
                "content": ARTICLE,
                "status": "published",
                "published_at": "2026-03-01 00:00:00+00",
            },
        ).scalar_one()
        conn.execute(
            lesson,
            {"title": "Withdrawn", "content": "Gone.", "status": "withdrawn", "published_at": None},
        )
        conn.execute(
            lesson, {"title": "Draft", "content": "", "status": "draft", "published_at": None}
        )
        question = conn.execute(
            text(
                "INSERT INTO quiz_questions (id, lesson_id, prompt, explanation) "
                "VALUES (gen_random_uuid(), :lesson, 'What is kopi O?', 'O means no milk.') "
                "RETURNING id"
            ),
            {"lesson": published},
        ).scalar_one()
        for position, (option, correct) in enumerate([("With milk", False), ("No milk", True)]):
            conn.execute(
                text(
                    "INSERT INTO quiz_options (id, question_id, text, is_correct, position) "
                    "VALUES (gen_random_uuid(), :question, :text, :correct, :position)"
                ),
                {"question": question, "text": option, "correct": correct, "position": position},
            )


def test_lessons_become_cards_and_published_ones_get_version_one():
    config = _config()
    command.downgrade(config, "0004")
    try:
        _insert_rows_at_0004()
        command.upgrade(config, "0005")

        with engine.connect() as conn:
            drafts = dict(conn.execute(text("SELECT title, draft FROM lessons")).all())
            versions = conn.execute(
                text(
                    "SELECT l.title, v.number, v.title, v.doc, v.published_at "
                    "FROM lesson_versions v "
                    "JOIN lessons l ON l.id = v.lesson_id ORDER BY l.title"
                )
            ).all()
    finally:
        command.upgrade(config, "head")

    # Every converted document is a valid lesson document.
    for doc in drafts.values():
        LessonDoc.model_validate(doc)

    cards = drafts["Published"]["cards"]
    assert [card["text"] for card in cards] == [
        "**Chope first, then order**\n\nPeople reserve a seat with a packet of tissues.\n\n"
        "**Kopi lingo**\n\n- **Kopi**: coffee with condensed milk\n- **Kopi O**: black coffee "
        "with sugar",
        "What is kopi O?",
    ]
    question = cards[-1]["question"]
    assert [(o["text"], o["correct"]) for o in question["options"]] == [
        ("With milk", False),
        ("No milk", True),
    ]
    assert question["explanation"] == "O means no milk."
    assert drafts["Withdrawn"]["cards"][0]["text"] == "Gone."
    assert drafts["Draft"] == {"cards": []}

    # Published and withdrawn lessons get version 1 with the same content; drafts get none.
    assert [(row[0], row[1], row[2]) for row in versions] == [
        ("Published", 1, "Published"),
        ("Withdrawn", 1, "Withdrawn"),
    ]
    assert versions[0][3] == drafts["Published"]
    assert versions[0][4].isoformat().startswith("2026-03-01")


def test_long_articles_are_split_into_readable_cards():
    config = _config()
    long_article = "\n\n".join(f"Paragraph {n} " + "word " * 80 for n in range(4))
    command.downgrade(config, "0004")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO lessons (id, title, content, status, position) "
                    "VALUES (gen_random_uuid(), 'Long', :content, 'draft', 0)"
                ),
                {"content": long_article},
            )
        command.upgrade(config, "0005")
        with engine.connect() as conn:
            cards = conn.execute(text("SELECT draft FROM lessons")).scalar_one()["cards"]
    finally:
        command.upgrade(config, "head")

    assert len(cards) == 4
    assert all(len(card["text"]) <= 600 for card in cards)
    assert [card["text"].split()[1] for card in cards] == ["0", "1", "2", "3"]
