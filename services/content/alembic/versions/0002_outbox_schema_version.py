"""Outbox: store each event's schema_version (the envelope used to hard-code 1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06 17:50:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbox",
        sa.Column("schema_version", sa.SmallInteger(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("outbox", "schema_version")
