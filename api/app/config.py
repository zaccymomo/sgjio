"""Application settings, read from environment variables or api/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_DIR / ".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://sgjio:sgjio@localhost:5432/sgjio"
    test_database_url: str = "postgresql+psycopg://sgjio:sgjio@localhost:5432/sgjio_test"

    # Front-end addresses, used to build links in emails
    web_url: str = "http://localhost:5173"
    admin_url: str = "http://localhost:5174"

    # Sessions and sign-in. Defaults are the team's proposed values (docs/decisions.md).
    cookie_secure: bool = False
    app_session_days: int = 7
    admin_session_hours: int = 8
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    reset_token_minutes: int = 5

    # Email
    email_backend: Literal["smtp", "console", "memory"] = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    email_from: str = "SGJio <no-reply@sgjio.example.com>"

    # Images and audio for lesson cards (SCRUM-19). Uploads larger than these are refused.
    media_max_image_mb: int = 15
    media_max_audio_mb: int = 10
    media_max_audio_seconds: int = 120

    # Seed accounts for local development
    seed_admin_email: str = "admin@sgjio.example.com"
    seed_admin_password: str = "AdminPass123"
    seed_user_email: str = "newcomer@sgjio.example.com"
    seed_user_password: str = "UserPass123"


@lru_cache
def get_settings() -> Settings:
    return Settings()
