"""Problems learners report in lessons (SCRUM-82, SCRUM-83).

Each report names the lesson, the version and the card it was sent from, a reason and an
optional note. Administrators mark it Fixed or Dismissed; it is kept either way.

Downgrade warning: every report is deleted.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-23 12:28:37.519317

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('lesson_reports',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('lesson_id', sa.UUID(), nullable=False),
    sa.Column('version_id', sa.UUID(), nullable=False),
    sa.Column('card_id', sa.String(length=40), nullable=False),
    sa.Column('reason', sa.Enum('wrong', 'insensitive', 'typo', 'media', 'other', name='report_reason', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('note', sa.String(length=500), server_default='', nullable=False),
    sa.Column('reporter_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Enum('open', 'fixed', 'dismissed', name='report_status', native_enum=False, create_constraint=True, length=20), server_default='open', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], name=op.f('fk_lesson_reports_lesson_id_lessons'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reporter_id'], ['users.id'], name=op.f('fk_lesson_reports_reporter_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], name=op.f('fk_lesson_reports_resolved_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['version_id'], ['lesson_versions.id'], name=op.f('fk_lesson_reports_version_id_lesson_versions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lesson_reports'))
    )
    op.create_index(op.f('ix_lesson_reports_lesson_id'), 'lesson_reports', ['lesson_id'], unique=False)
    op.create_index('ix_lesson_reports_status_created_at', 'lesson_reports', ['status', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_lesson_reports_status_created_at', table_name='lesson_reports')
    op.drop_index(op.f('ix_lesson_reports_lesson_id'), table_name='lesson_reports')
    op.drop_table('lesson_reports')
