"""A description for each topic (SCRUM-86).

Adds `description`, a line or two shown under the topic's name on its page. Existing
topics get an empty one, which means "no description"; the seed fills in the seeded
topics' next time it runs.

Downgrade warning: dropping the column forgets every description administrators wrote.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23 16:40:50.854667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('topics', sa.Column('description', sa.String(length=200), server_default='', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('topics', 'description')
