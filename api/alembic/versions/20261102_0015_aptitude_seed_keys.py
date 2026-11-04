"""Stable keys for aptitude questions loaded from version-controlled seed content.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("aptitude_questions", sa.Column("seed_key", sa.String(120), nullable=True))
    op.create_unique_constraint(
        op.f("uq_aptitude_questions_seed_key"), "aptitude_questions", ["seed_key"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_aptitude_questions_seed_key"), "aptitude_questions", type_="unique")
    op.drop_column("aptitude_questions", "seed_key")
