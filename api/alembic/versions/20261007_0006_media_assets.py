"""Images and audio for lesson cards (SCRUM-19).

One row per uploaded file, with the file itself, so media is backed up and reset with the
rest of the database. Lesson documents refer to these rows by id.

Downgrade warning: every uploaded image and audio file is deleted.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-07 10:41:48.600762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('media_assets',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.Enum('image', 'audio', name='media_kind', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('mime', sa.String(length=60), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('placeholder', sa.String(length=2000), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_media_assets_created_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media_assets')),
    sa.UniqueConstraint('sha256', name=op.f('uq_media_assets_sha256'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('media_assets')
