"""Topic archiving (SCRUM-57).

Adds a nullable `archived_at` to topics. Empty means active; a timestamp means the topic
was archived then. Existing rows stay active, so there is no backfill.

Downgrade warning: dropping the column forgets which topics were archived, so every
archived topic becomes active again and reappears for users.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01 21:50:21.282377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('topics', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('topics', 'archived_at')
