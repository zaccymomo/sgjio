"""Notification's settings, read from environment variables or services/notification/.env.

docker-compose.yml sets every one of them for the container. The plumbing's own settings
(SERVICE_NAME, BROKER_URL, RUN_CONSUMER, LOG_LEVEL) are read by app/platform/config.py.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=SERVICE_DIR / ".env", extra="ignore")

    # Database: only the processed_events inbox (compose notification-db, host port 5436)
    database_url: str = "postgresql+psycopg://notification:notification@localhost:5436/notification"
    test_database_url: str = (
        "postgresql+psycopg://notification:notification@localhost:5436/notification_test"
    )

    # Email (moved unchanged from the monolith)
    email_backend: Literal["smtp", "console", "memory"] = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    email_from: str = "SGJio <no-reply@sgjio.example.com>"


@lru_cache
def get_settings() -> Settings:
    return Settings()
