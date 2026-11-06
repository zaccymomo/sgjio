"""Content's settings, read from environment variables (docker-compose.yml) or a .env file
in services/content.

The plumbing's own settings (SERVICE_NAME, GATEWAY_KEY, BROKER_URL, RUN_RELAY, RUN_CONSUMER)
are read by app.platform.config.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_DIR = Path(__file__).resolve().parent.parent
# On the host the lesson files are in the repository's content/ folder; in compose they are
# mounted at /srv/content and CONTENT_DIR says so.
_REPO_CONTENT = SERVICE_DIR.parent.parent / "content" / "lessons"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=SERVICE_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://content:content@localhost:5434/content"
    test_database_url: str = "postgresql+psycopg://content:content@localhost:5434/content_test"

    # Images and audio for lesson cards (SCRUM-19). Uploads larger than these are refused.
    media_max_image_mb: int = 15
    media_max_audio_mb: int = 10
    media_max_audio_seconds: int = 120

    # Lesson files loaded by the seed and `python -m app.cli import-lessons`
    # (content/README.md). The aptitude bank is content_dir.parent / aptitude_questions.yaml.
    content_dir: Path = _REPO_CONTENT


@lru_cache
def get_settings() -> Settings:
    return Settings()
