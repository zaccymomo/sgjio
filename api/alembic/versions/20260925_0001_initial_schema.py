"""Initial schema (SCRUM-72).

Users and profiles, topics, lessons with their quiz question and options, plus the
tables behind sign-in: sessions, password reset tokens and login attempts.

Revision ID: 0001
Revises: 
Create Date: 2026-09-25 15:12:35.715365

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('login_attempts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('scope', sa.Enum('app', 'admin', name='auth_scope', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('succeeded', sa.Boolean(), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_login_attempts'))
    )
    op.create_index('ix_login_attempts_lookup', 'login_attempts', ['email', 'scope', 'attempted_at'], unique=False)
    op.create_table('topics',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_topics'))
    )
    op.create_index('uq_topics_name_lower', 'topics', [sa.literal_column('lower(name)')], unique=True)
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('user', 'admin', name='user_role', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('user_type', sa.Enum('newcomer', 'singaporean', name='user_type', native_enum=False, create_constraint=True, length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('auth_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('scope', sa.Enum('app', 'admin', name='auth_scope', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_auth_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_auth_sessions_token_hash'))
    )
    op.create_index(op.f('ix_auth_sessions_user_id'), 'auth_sessions', ['user_id'], unique=False)
    op.create_table('lessons',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('topic_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Enum('draft', 'published', 'withdrawn', name='lesson_status', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_lessons_topic_id_topics'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lessons'))
    )
    op.create_index(op.f('ix_lessons_status'), 'lessons', ['status'], unique=False)
    op.create_index(op.f('ix_lessons_topic_id'), 'lessons', ['topic_id'], unique=False)
    op.create_index(op.f('ix_lessons_updated_at'), 'lessons', ['updated_at'], unique=False)
    op.create_table('password_reset_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('scope', sa.Enum('app', 'admin', name='auth_scope', native_enum=False, create_constraint=True, length=20), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_password_reset_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_password_reset_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_password_reset_tokens_token_hash'))
    )
    op.create_index(op.f('ix_password_reset_tokens_user_id'), 'password_reset_tokens', ['user_id'], unique=False)
    op.create_table('profiles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('neighbourhood', sa.String(length=120), nullable=True),
    sa.Column('interests', sa.ARRAY(sa.String(length=60)), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('languages', sa.ARRAY(sa.String(length=60)), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_profiles'))
    )
    op.create_table('quiz_questions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('lesson_id', sa.UUID(), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], name=op.f('fk_quiz_questions_lesson_id_lessons'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz_questions')),
    sa.UniqueConstraint('lesson_id', name=op.f('uq_quiz_questions_lesson_id'))
    )
    op.create_table('quiz_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('question_id', sa.UUID(), nullable=False),
    sa.Column('text', sa.String(length=300), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['quiz_questions.id'], name=op.f('fk_quiz_options_question_id_quiz_questions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quiz_options'))
    )
    op.create_index(op.f('ix_quiz_options_question_id'), 'quiz_options', ['question_id'], unique=False)
    op.create_index('uq_quiz_options_one_correct', 'quiz_options', ['question_id'], unique=True, postgresql_where=sa.text('is_correct'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_quiz_options_one_correct', table_name='quiz_options', postgresql_where=sa.text('is_correct'))
    op.drop_index(op.f('ix_quiz_options_question_id'), table_name='quiz_options')
    op.drop_table('quiz_options')
    op.drop_table('quiz_questions')
    op.drop_table('profiles')
    op.drop_index(op.f('ix_password_reset_tokens_user_id'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    op.drop_index(op.f('ix_lessons_updated_at'), table_name='lessons')
    op.drop_index(op.f('ix_lessons_topic_id'), table_name='lessons')
    op.drop_index(op.f('ix_lessons_status'), table_name='lessons')
    op.drop_table('lessons')
    op.drop_index(op.f('ix_auth_sessions_user_id'), table_name='auth_sessions')
    op.drop_table('auth_sessions')
    op.drop_table('users')
    op.drop_index('uq_topics_name_lower', table_name='topics')
    op.drop_table('topics')
    op.drop_index('ix_login_attempts_lookup', table_name='login_attempts')
    op.drop_table('login_attempts')
