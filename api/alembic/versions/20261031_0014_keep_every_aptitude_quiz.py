"""Keep every aptitude quiz (SCRUM-110 AC4, SCRUM-102).

0013 kept only each user's latest quiz, in `users.quiz_results` and `users.quiz_taken_at`.
This keeps them all instead:

- `aptitude_attempts`: one row per quiz taken, never overwritten, with when it was taken,
  the level it gave and its results (each answer with its own copy of the question, as
  before). Users are shown the newest; the rest are history.
- Any quiz already saved on a user is moved into it, with the user's level as the level
  it gave, and the two `users` columns are dropped.

`users.level` stays: it is the current level, which level-ups (SCRUM-105) can raise
after a quiz.

Downgrade warning: only each user's latest quiz is put back on `users`; earlier quizzes
are lost.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-31 12:35:59.291394

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('aptitude_attempts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('taken_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('level', sa.SmallInteger(), nullable=False),
    sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("jsonb_typeof(results) = 'array'", name=op.f('ck_aptitude_attempts_results_list')),
    sa.CheckConstraint('level BETWEEN 1 AND 5', name=op.f('ck_aptitude_attempts_level_range')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_aptitude_attempts_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_aptitude_attempts'))
    )
    op.create_index('ix_aptitude_attempts_user_id_taken_at', 'aptitude_attempts', ['user_id', 'taken_at'], unique=False)
    op.execute(
        "INSERT INTO aptitude_attempts (id, user_id, taken_at, level, results) "
        "SELECT gen_random_uuid(), id, quiz_taken_at, COALESCE(level, 1), quiz_results "
        "FROM users WHERE quiz_results IS NOT NULL"
    )
    op.drop_constraint(op.f('ck_users_quiz_results_with_time'), 'users', type_='check')
    op.drop_column('users', 'quiz_results')
    op.drop_column('users', 'quiz_taken_at')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('quiz_taken_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('quiz_results', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True))
    # Each user's latest quiz goes back on their row; earlier ones are lost.
    op.execute(
        "UPDATE users SET quiz_results = latest.results, quiz_taken_at = latest.taken_at "
        "FROM (SELECT DISTINCT ON (user_id) user_id, results, taken_at FROM aptitude_attempts "
        "ORDER BY user_id, taken_at DESC, id DESC) AS latest WHERE users.id = latest.user_id"
    )
    op.create_check_constraint(
        op.f('ck_users_quiz_results_with_time'), 'users',
        '(quiz_results IS NULL) = (quiz_taken_at IS NULL)',
    )
    op.drop_index('ix_aptitude_attempts_user_id_taken_at', table_name='aptitude_attempts')
    op.drop_table('aptitude_attempts')
