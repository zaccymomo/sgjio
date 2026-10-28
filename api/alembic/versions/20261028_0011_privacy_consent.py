"""Record the privacy notice version and consent time for new registrations.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("privacy_agreed_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("privacy_notice_version", sa.String(length=32)))


def downgrade() -> None:
    op.drop_column("users", "privacy_notice_version")
    op.drop_column("users", "privacy_agreed_at")
