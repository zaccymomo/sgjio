"""Treat accounts made before the introduction as having seen it (SCRUM-94).

The main app now shows a short introduction while `users.intro_finished_at` is empty. That
column has been empty for everyone since 0013, so without this people already using the
app would be sent through an introduction meant for their first sign-in. Data only: no
schema change.

Downgrade leaves the values as they are: they are harmless with the column still there.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-05 10:00:00

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET intro_finished_at = created_at "
        "WHERE role = 'user' AND intro_finished_at IS NULL"
    )


def downgrade() -> None:
    pass
