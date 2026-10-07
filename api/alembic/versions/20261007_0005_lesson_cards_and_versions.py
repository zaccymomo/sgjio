"""Lessons become decks of cards, with published versions (SCRUM-19, SCRUM-52).

A lesson's text and its one quiz question move into a JSON document of cards, stored on
the lesson as its working draft (`lessons.draft`). Publishing copies the draft into
`lesson_versions`, which is what users see. See app/lesson_doc.py for the document.

Existing lessons are converted, not lost:

- the text becomes one or more text cards, split at blank lines into cards of a readable
  length; "## Headings" become bold lines, since cards have no headings
- the quiz question becomes a final card: the prompt as its text, its options (the correct
  one marked) and its explanation
- every lesson that is published or withdrawn, or was ever published, gets version 1 with
  that content, so users keep seeing exactly what they saw

The conversion is written out here rather than imported from the app, so this migration
keeps doing the same thing however the app changes later.

Downgrade warning: only the first question survives a downgrade, versions are dropped, and
text cards are joined back into one body.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07 10:00:00.000000

"""
import json
import re
import secrets
import string
import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cards hold at most 1,500 characters; aim well below that so a card stays readable.
CARD_TARGET = 600
CARD_MAX = 1500
_ALPHABET = string.ascii_letters + string.digits


def _id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


def _text_cards(content: str) -> list[dict]:
    content = re.sub(r"^#{1,6}[ \t]+(.+?)[ \t]*$", r"**\1**", content.strip(), flags=re.MULTILINE)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        while len(paragraph) > CARD_MAX:
            cut = paragraph.rfind(" ", 0, CARD_MAX)
            cut = cut if cut > 0 else CARD_MAX
            chunks.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        # A bold line on its own (a former heading) stays with what follows it.
        if chunks and (
            len(chunks[-1]) + len(paragraph) + 2 <= CARD_TARGET or re.fullmatch(r"\*\*.+\*\*", chunks[-1])
        ):
            chunks[-1] = f"{chunks[-1]}\n\n{paragraph}"
        else:
            chunks.append(paragraph)
    return [
        {"type": "story", "id": _id(), "text": text, "image": None, "audio": None, "question": None}
        for text in chunks
    ]


def _question_card(prompt: str, explanation: str, options: list[tuple[str, bool]]) -> dict:
    return {
        "type": "story",
        "id": _id(),
        "text": prompt,
        "image": None,
        "audio": None,
        "question": {
            "type": "choice",
            "id": _id(),
            "options": [
                {"id": _id(), "text": text[:160], "correct": correct, "why_not": ""}
                for text, correct in options
            ],
            "explanation": explanation[:800],
            "shuffle": True,
        },
    }


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('lesson_versions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('lesson_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('summary', sa.String(length=160), nullable=False),
    sa.Column('doc', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('published_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], name=op.f('fk_lesson_versions_lesson_id_lessons'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['published_by'], ['users.id'], name=op.f('fk_lesson_versions_published_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lesson_versions')),
    sa.UniqueConstraint('lesson_id', 'number', name=op.f('uq_lesson_versions_lesson_id'))
    )
    op.create_index(op.f('ix_lesson_versions_lesson_id'), 'lesson_versions', ['lesson_id'], unique=False)

    op.add_column('lessons', sa.Column('key', sa.String(length=200), nullable=True))
    op.add_column('lessons', sa.Column('summary', sa.String(length=160), server_default='', nullable=False))
    op.add_column('lessons', sa.Column('draft', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text('\'{"cards": []}\'::jsonb'), nullable=False))
    op.add_column('lessons', sa.Column('has_unpublished_changes', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_unique_constraint(op.f('uq_lessons_key'), 'lessons', ['key'])

    conn = op.get_bind()
    lessons = conn.execute(sa.text(
        "SELECT id, title, content, status, published_at, updated_at FROM lessons"
    )).all()
    for lesson in lessons:
        cards = _text_cards(lesson.content or "")
        question = conn.execute(
            sa.text("SELECT id, prompt, explanation FROM quiz_questions WHERE lesson_id = :id"),
            {"id": lesson.id},
        ).first()
        if question is not None:
            options = conn.execute(
                sa.text(
                    "SELECT text, is_correct FROM quiz_options WHERE question_id = :id "
                    "ORDER BY position, id"
                ),
                {"id": question.id},
            ).all()
            cards.append(_question_card(
                question.prompt, question.explanation, [(o.text, o.is_correct) for o in options]
            ))
        doc = json.dumps({"cards": cards[:30]})
        conn.execute(
            sa.text("UPDATE lessons SET draft = CAST(:doc AS jsonb) WHERE id = :id"),
            {"doc": doc, "id": lesson.id},
        )
        if lesson.status in ("published", "withdrawn") or lesson.published_at is not None:
            conn.execute(
                sa.text(
                    "INSERT INTO lesson_versions "
                    "(id, lesson_id, number, title, summary, doc, published_at) "
                    "VALUES (:id, :lesson_id, 1, :title, '', CAST(:doc AS jsonb), :published_at)"
                ),
                {
                    "id": uuid.uuid4(),
                    "lesson_id": lesson.id,
                    "title": lesson.title,
                    "doc": doc,
                    "published_at": lesson.published_at or lesson.updated_at or datetime.now(UTC),
                },
            )

    op.drop_index('uq_quiz_options_one_correct', table_name='quiz_options', postgresql_where=sa.text('is_correct'))
    op.drop_index(op.f('ix_quiz_options_question_id'), table_name='quiz_options')
    op.drop_table('quiz_options')
    op.drop_table('quiz_questions')
    op.drop_column('lessons', 'content')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('lessons', sa.Column('content', sa.TEXT(), server_default='', nullable=False))
    op.create_table('quiz_questions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('lesson_id', sa.UUID(), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], name=op.f('fk_quiz_questions_lesson_id_lessons'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz_questions')),
    sa.UniqueConstraint('lesson_id', name=op.f('uq_quiz_questions_lesson_id'))
    )
    op.create_table('quiz_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('question_id', sa.UUID(), nullable=False),
    sa.Column('text', sa.String(length=300), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['quiz_questions.id'], name=op.f('fk_quiz_options_question_id_quiz_questions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz_options'))
    )
    op.create_index(op.f('ix_quiz_options_question_id'), 'quiz_options', ['question_id'], unique=False)
    op.create_index('uq_quiz_options_one_correct', 'quiz_options', ['question_id'], unique=True, postgresql_where=sa.text('is_correct'))

    conn = op.get_bind()
    for lesson in conn.execute(sa.text("SELECT id, draft FROM lessons")).all():
        cards = (lesson.draft or {}).get("cards", [])
        texts = [card.get("text", "") for card in cards if not card.get("question")]
        conn.execute(
            sa.text("UPDATE lessons SET content = :content WHERE id = :id"),
            {"content": "\n\n".join(t for t in texts if t), "id": lesson.id},
        )
        asked = next((card for card in cards if card.get("question")), None)
        if asked is None:
            continue
        question_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO quiz_questions (id, lesson_id, prompt, explanation) "
                "VALUES (:id, :lesson_id, :prompt, :explanation)"
            ),
            {
                "id": question_id,
                "lesson_id": lesson.id,
                "prompt": asked.get("text", ""),
                "explanation": asked["question"].get("explanation", ""),
            },
        )
        seen_correct = False
        for position, option in enumerate(asked["question"].get("options", [])):
            correct = bool(option.get("correct")) and not seen_correct
            seen_correct = seen_correct or correct
            conn.execute(
                sa.text(
                    "INSERT INTO quiz_options (id, question_id, text, is_correct, position) "
                    "VALUES (:id, :question_id, :text, :correct, :position)"
                ),
                {
                    "id": uuid.uuid4(),
                    "question_id": question_id,
                    "text": option.get("text", ""),
                    "correct": correct,
                    "position": position,
                },
            )

    op.drop_constraint(op.f('uq_lessons_key'), 'lessons', type_='unique')
    op.drop_column('lessons', 'has_unpublished_changes')
    op.drop_column('lessons', 'draft')
    op.drop_column('lessons', 'summary')
    op.drop_column('lessons', 'key')
    op.drop_index(op.f('ix_lesson_versions_lesson_id'), table_name='lesson_versions')
    op.drop_table('lesson_versions')
