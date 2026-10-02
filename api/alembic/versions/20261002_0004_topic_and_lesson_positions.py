"""Topic and lesson order (SCRUM-66).

Adds `position` to topics and lessons, so administrators can set the order of topics
(which is also the order of users' progress circles) and of lessons within a topic.

Existing rows are numbered from 0 in the order they were created, ties broken by name or
title (and finally id, so the result is deterministic). Lessons are numbered per topic,
and lessons with no topic form one group of their own (Postgres puts NULLs in a single
partition). The seed creates everything in one transaction, so its rows share a
`created_at` and come out alphabetical; that is expected, and an administrator can
reorder them.

Positions are a sort key, not unique: there is no unique constraint, and every read
breaks ties by `created_at`.

Downgrade warning: dropping the columns forgets the order administrators set.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-02 00:21:39.675202

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable first, so existing rows can be numbered before the constraint applies.
    op.add_column('topics', sa.Column('position', sa.Integer(), nullable=True))
    op.add_column('lessons', sa.Column('position', sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE topics AS t
        SET position = numbered.n
        FROM (
            SELECT id, row_number() OVER (ORDER BY created_at, name, id) - 1 AS n
            FROM topics
        ) AS numbered
        WHERE t.id = numbered.id
        """
    )
    op.execute(
        """
        UPDATE lessons AS l
        SET position = numbered.n
        FROM (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY topic_id ORDER BY created_at, title, id
                   ) - 1 AS n
            FROM lessons
        ) AS numbered
        WHERE l.id = numbered.id
        """
    )

    op.alter_column('topics', 'position', nullable=False)
    op.alter_column('lessons', 'position', nullable=False)
    op.create_index('ix_lessons_topic_id_position', 'lessons', ['topic_id', 'position'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_lessons_topic_id_position', table_name='lessons')
    op.drop_column('lessons', 'position')
    op.drop_column('topics', 'position')
