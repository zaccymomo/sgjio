"""Signing in with Google (SCRUM-92).

- `users.google_sub`: Google's own id for the account, set the first time someone signs in
  with Google. Unique, so one Google account is linked to at most one SGJio account.
- `users.password_hash` may now be empty: an account created with Google has no password.

Existing rows need no backfill: every existing account has a password and no Google link.

Downgrade warning: accounts created with Google are given a password nobody knows, so they
cannot sign in until they use "Forgot password". Every Google link is lost.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-29 16:39:29.849368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('google_sub', sa.String(length=255), nullable=True))
    op.alter_column('users', 'password_hash',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    op.create_unique_constraint(op.f('uq_users_google_sub'), 'users', ['google_sub'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('uq_users_google_sub'), 'users', type_='unique')
    # Not a valid Argon2 hash, so verify_password() never accepts any password for it.
    op.execute("UPDATE users SET password_hash = '!google-only' WHERE password_hash IS NULL")
    op.alter_column('users', 'password_hash',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
    op.drop_column('users', 'google_sub')
