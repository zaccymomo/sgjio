"""Stable keys for aptitude questions loaded from version-controlled seed content.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Some development databases saw this branch's old duplicate revision 0015 before
    # main's real 0015 was merged. They already have this column and constraint, although
    # Alembic now reaches them through 0017. Fresh databases take the normal path below.
    schema = sa.inspect(op.get_bind())
    columns = {column["name"] for column in schema.get_columns("aptitude_questions")}
    if "seed_key" not in columns:
        op.add_column("aptitude_questions", sa.Column("seed_key", sa.String(120), nullable=True))
    constraints = {
        constraint["name"] for constraint in schema.get_unique_constraints("aptitude_questions")
    }
    if op.f("uq_aptitude_questions_seed_key") not in constraints:
        op.create_unique_constraint(
            op.f("uq_aptitude_questions_seed_key"), "aptitude_questions", ["seed_key"]
        )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_aptitude_questions_seed_key"), "aptitude_questions", type_="unique")
    op.drop_column("aptitude_questions", "seed_key")
