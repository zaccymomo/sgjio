"""Migration 0012 lets accounts created with Google have no password (SCRUM-92).

Downgrading must not fail on those accounts, and must not leave them a usable password."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db import engine
from app.security import verify_password

API_DIR = Path(__file__).resolve().parent.parent


def _config() -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    return config


def test_downgrade_gives_google_only_accounts_a_password_nobody_knows():
    config = _config()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, name, email, password_hash, google_sub, role) VALUES "
                "(gen_random_uuid(), 'G', 'g@example.com', NULL, 'g-1', 'user')"
            )
        )
    try:
        command.downgrade(config, "0011")
        with engine.connect() as conn:
            stored = conn.execute(
                text("SELECT password_hash FROM users WHERE email = 'g@example.com'")
            ).scalar_one()
        assert stored
        assert not verify_password(stored, stored)
        assert not verify_password("", stored)
    finally:
        command.upgrade(config, "head")
