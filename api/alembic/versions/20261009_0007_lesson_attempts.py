"""Learners' attempts at lessons, and scores instead of right-or-wrong (SCRUM-16).

Each run through a lesson's deck is an attempt, tied to the version shown, with the first
answer to each question. Completions now keep the best score (first-try correct answers out
of the scored questions) instead of one right-or-wrong result. An existing completion
becomes 1 of 1 if it was answered correctly and 0 of 1 if not.

Downgrade warning: every attempt and answer is deleted, and a best score becomes "answered
correctly" only if it was full marks.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-09 03:32:25.793199

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('lesson_attempts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('lesson_id', sa.UUID(), nullable=False),
    sa.Column('version_id', sa.UUID(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('correct', sa.Integer(), nullable=True),
    sa.Column('scored', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], name=op.f('fk_lesson_attempts_lesson_id_lessons'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_lesson_attempts_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['version_id'], ['lesson_versions.id'], name=op.f('fk_lesson_attempts_version_id_lesson_versions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lesson_attempts'))
    )
    op.create_index('ix_lesson_attempts_user_id_lesson_id', 'lesson_attempts', ['user_id', 'lesson_id'], unique=False)
    op.create_table('attempt_answers',
    sa.Column('attempt_id', sa.UUID(), nullable=False),
    sa.Column('question_id', sa.String(length=40), nullable=False),
    sa.Column('option_id', sa.String(length=40), nullable=False),
    sa.Column('correct', sa.Boolean(), nullable=False),
    sa.Column('scored', sa.Boolean(), nullable=False),
    sa.Column('answered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['attempt_id'], ['lesson_attempts.id'], name=op.f('fk_attempt_answers_attempt_id_lesson_attempts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('attempt_id', 'question_id', name=op.f('pk_attempt_answers'))
    )

    # Existing completions: one right-or-wrong question becomes 1 of 1 or 0 of 1.
    op.add_column('lesson_completions', sa.Column('best_correct', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('lesson_completions', sa.Column('best_scored', sa.Integer(), nullable=False, server_default='1'))
    op.execute("UPDATE lesson_completions SET best_correct = CASE WHEN answered_correctly THEN 1 ELSE 0 END")
    op.alter_column('lesson_completions', 'best_correct', server_default=None)
    op.alter_column('lesson_completions', 'best_scored', server_default=None)
    op.add_column('lesson_completions', sa.Column('best_attempt_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_lesson_completions_best_attempt_id_lesson_attempts'), 'lesson_completions', 'lesson_attempts', ['best_attempt_id'], ['id'], ondelete='SET NULL')
    op.drop_column('lesson_completions', 'answered_correctly')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('lesson_completions', sa.Column('answered_correctly', sa.BOOLEAN(), autoincrement=False, nullable=False, server_default=sa.false()))
    op.execute("UPDATE lesson_completions SET answered_correctly = (best_correct = best_scored)")
    op.alter_column('lesson_completions', 'answered_correctly', server_default=None)
    op.drop_constraint(op.f('fk_lesson_completions_best_attempt_id_lesson_attempts'), 'lesson_completions', type_='foreignkey')
    op.drop_column('lesson_completions', 'best_attempt_id')
    op.drop_column('lesson_completions', 'best_scored')
    op.drop_column('lesson_completions', 'best_correct')
    op.drop_table('attempt_answers')
    op.drop_index('ix_lesson_attempts_user_id_lesson_id', table_name='lesson_attempts')
    op.drop_table('lesson_attempts')
