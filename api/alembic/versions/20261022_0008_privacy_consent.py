"""Record the privacy notice version and consent time for new registrations.

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("privacy_agreed_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("privacy_notice_version", sa.String(length=32)))


def downgrade() -> None:
    op.drop_column("users", "privacy_notice_version")
    op.drop_column("users", "privacy_agreed_at")
