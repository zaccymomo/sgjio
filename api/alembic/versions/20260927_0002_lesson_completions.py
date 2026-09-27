"""Lesson completions (SCRUM-16).

One row per lesson a user has finished, which is the "completed" half of every progress
circle on the landing page (SCRUM-43).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27 13:23:15.611520

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('lesson_completions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('lesson_id', sa.UUID(), nullable=False),
    sa.Column('answered_correctly', sa.Boolean(), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], name=op.f('fk_lesson_completions_lesson_id_lessons'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_lesson_completions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lesson_completions')),
    # Completion counts once however many times the quiz is retaken (SCRUM-16 AC5, AC6).
    sa.UniqueConstraint('user_id', 'lesson_id', name=op.f('uq_lesson_completions_user_id'))
    )
    op.create_index(op.f('ix_lesson_completions_lesson_id'), 'lesson_completions', ['lesson_id'], unique=False)
    op.create_index(op.f('ix_lesson_completions_user_id'), 'lesson_completions', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_lesson_completions_user_id'), table_name='lesson_completions')
    op.drop_index(op.f('ix_lesson_completions_lesson_id'), table_name='lesson_completions')
    op.drop_table('lesson_completions')
