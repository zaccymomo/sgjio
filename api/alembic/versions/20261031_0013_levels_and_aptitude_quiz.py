"""Levels and the aptitude quiz (SCRUM-110, Epic 6).

Users, lessons and aptitude questions share one scale of Level 1 to 5.

- `lessons.level`: required. Every existing lesson starts at Level 1 (SCRUM-103 AC4): the
  column is added with a default of 1 to fill existing rows, and the default is then
  dropped, so a lesson written without a level is refused (SCRUM-110 AC3).
- `aptitude_questions`: the quiz's question bank (SCRUM-96), with a topic, a level, the
  options and the one correct option, which must be among the options.
- `users.level`: one level for the whole app (SCRUM-99), empty until the first quiz.
- `users.quiz_results` and `users.quiz_taken_at`: the latest quiz only, replaced by a
  retake (SCRUM-102). Each answer keeps its own copy of the question (SCRUM-110 AC5).
- `users.intro_finished_at`: when the introduction was finished or skipped (SCRUM-94).

Downgrade warning: every lesson's level, the question bank, users' levels and quiz results
are lost. Nothing else changes.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-31 11:23:30.304417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('aptitude_questions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('topic_id', sa.UUID(), nullable=False),
    sa.Column('level', sa.SmallInteger(), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('correct_option_id', sa.String(length=40), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("jsonb_typeof(options) = 'array'", name=op.f('ck_aptitude_questions_options_list')),
    sa.CheckConstraint("options @> jsonb_build_array(jsonb_build_object('id', correct_option_id))", name=op.f('ck_aptitude_questions_correct_option_listed')),
    sa.CheckConstraint('level BETWEEN 1 AND 5', name=op.f('ck_aptitude_questions_level_range')),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_aptitude_questions_topic_id_topics'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_aptitude_questions'))
    )
    op.create_index('ix_aptitude_questions_level_is_active', 'aptitude_questions', ['level', 'is_active'], unique=False)
    op.create_index(op.f('ix_aptitude_questions_topic_id'), 'aptitude_questions', ['topic_id'], unique=False)
    # Existing lessons get Level 1 (SCRUM-103 AC4); new ones must name a level.
    op.add_column('lessons', sa.Column('level', sa.SmallInteger(), server_default='1', nullable=False))
    op.alter_column('lessons', 'level', server_default=None)
    op.create_check_constraint(op.f('ck_lessons_level_range'), 'lessons', 'level BETWEEN 1 AND 5')
    op.add_column('users', sa.Column('intro_finished_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('level', sa.SmallInteger(), nullable=True))
    op.add_column('users', sa.Column('quiz_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('users', sa.Column('quiz_taken_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(op.f('ck_users_level_range'), 'users', 'level BETWEEN 1 AND 5')
    op.create_check_constraint(
        op.f('ck_users_quiz_results_with_time'), 'users',
        '(quiz_results IS NULL) = (quiz_taken_at IS NULL)',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_users_quiz_results_with_time'), 'users', type_='check')
    op.drop_constraint(op.f('ck_users_level_range'), 'users', type_='check')
    op.drop_column('users', 'quiz_taken_at')
    op.drop_column('users', 'quiz_results')
    op.drop_column('users', 'level')
    op.drop_column('users', 'intro_finished_at')
    op.drop_constraint(op.f('ck_lessons_level_range'), 'lessons', type_='check')
    op.drop_column('lessons', 'level')
    op.drop_index(op.f('ix_aptitude_questions_topic_id'), table_name='aptitude_questions')
    op.drop_index('ix_aptitude_questions_level_is_active', table_name='aptitude_questions')
    op.drop_table('aptitude_questions')
