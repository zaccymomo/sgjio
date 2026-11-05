"""Replace the user level with per-topic exemptions (SCRUM-113, Epic 6).

The aptitude quiz now assesses each topic separately and is taken once, so:

- `users.level` is dropped: users no longer have one level for the whole app (AC1, AC4).
- `topic_exemptions` is added: for each user and topic, the highest level they are
  exempted up to, 0 to 5 (AC1, AC3), one per topic (AC2). Exempted lessons are worked out
  from it and each lesson's level, not stored (AC5, `app/exemptions.py`). Its `user_id`
  refers to both the user and their quiz, so exemptions only exist beside a completed quiz.
- `aptitude_attempts` allows one quiz per user (AC2), and loses `level`, the single level
  a quiz used to give. Each quiz's `results` (every question's topic, level, option chosen
  and whether it was right) are kept as they are (AC4).

Existing data: lesson completions are untouched (AC4). A user who somehow has more than one
quiz from the old retake design keeps their latest; the old quiz screens were never built,
so none should exist. Old quizzes give no exemptions, as they did not assess each topic.

Downgrade restores the schema (AC6): `users.level` comes back empty, each quiz gets Level 1,
and exemptions are lost.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-05 01:54:29.948785

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # One quiz per user: keep each user's latest if the old design left more than one.
    op.execute(
        "DELETE FROM aptitude_attempts WHERE id NOT IN ("
        "SELECT DISTINCT ON (user_id) id FROM aptitude_attempts "
        "ORDER BY user_id, taken_at DESC, id DESC)"
    )
    op.drop_index(op.f('ix_aptitude_attempts_user_id_taken_at'), table_name='aptitude_attempts')
    op.create_unique_constraint(op.f('uq_aptitude_attempts_user_id'), 'aptitude_attempts', ['user_id'])
    # Dropping a column drops its CHECK too (ck_*_level_range).
    op.drop_column('aptitude_attempts', 'level')
    op.drop_column('users', 'level')

    op.create_table('topic_exemptions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('topic_id', sa.UUID(), nullable=False),
    sa.Column('level', sa.SmallInteger(), nullable=False),
    sa.CheckConstraint('level BETWEEN 0 AND 5', name=op.f('ck_topic_exemptions_level_range')),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_topic_exemptions_topic_id_topics'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['aptitude_attempts.user_id'], name=op.f('fk_topic_exemptions_user_id_aptitude_attempts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_topic_exemptions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'topic_id', name=op.f('pk_topic_exemptions'))
    )
    op.create_index(op.f('ix_topic_exemptions_topic_id'), 'topic_exemptions', ['topic_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_topic_exemptions_topic_id'), table_name='topic_exemptions')
    op.drop_table('topic_exemptions')

    op.add_column('users', sa.Column('level', sa.SmallInteger(), nullable=True))
    op.create_check_constraint(op.f('ck_users_level_range'), 'users', 'level BETWEEN 1 AND 5')
    # Each kept quiz needs a level again; the old design's lowest is the safe one.
    op.add_column('aptitude_attempts', sa.Column('level', sa.SmallInteger(), server_default='1', nullable=False))
    op.alter_column('aptitude_attempts', 'level', server_default=None)
    op.create_check_constraint(op.f('ck_aptitude_attempts_level_range'), 'aptitude_attempts', 'level BETWEEN 1 AND 5')
    op.drop_constraint(op.f('uq_aptitude_attempts_user_id'), 'aptitude_attempts', type_='unique')
    op.create_index(op.f('ix_aptitude_attempts_user_id_taken_at'), 'aptitude_attempts', ['user_id', 'taken_at'], unique=False)
