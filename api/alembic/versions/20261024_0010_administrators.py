"""Adding and removing administrators from the portal (SCRUM-81).

Adds two nullable timestamps to users:

- `invited_at`: an administrator invited from the portal who has not yet chosen a password.
- `removed_at`: an administrator removed from the portal. The account is kept, closed, so it
  can be restored.

and `admin_events`, the activity log of those changes. Existing rows need no backfill:
every existing administrator is active and has chosen a password.

Downgrade warning: removed administrators count as administrators again. Removal replaced
their password with one nobody knows, so they still cannot sign in until someone sends them
a reset link. The activity log is lost.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-24 01:10:53.063254

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('admin_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('action', sa.Enum('invited', 'invite_resent', 'joined', 'invite_cancelled', 'removed', 'restored', 'added', name='admin_action', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('admin_id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_admin_events_actor_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['admin_id'], ['users.id'], name=op.f('fk_admin_events_admin_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_events'))
    )
    op.create_index(op.f('ix_admin_events_admin_id'), 'admin_events', ['admin_id'], unique=False)
    op.create_index(op.f('ix_admin_events_created_at'), 'admin_events', ['created_at'], unique=False)
    op.add_column('users', sa.Column('invited_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'removed_at')
    op.drop_column('users', 'invited_at')
    op.drop_index(op.f('ix_admin_events_created_at'), table_name='admin_events')
    op.drop_index(op.f('ix_admin_events_admin_id'), table_name='admin_events')
    op.drop_table('admin_events')
