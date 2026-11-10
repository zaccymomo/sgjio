"""Generation's settings, read from environment variables or services/generation/.env.

docker-compose.yml sets every one of them for the container (from the host's environment,
with safe defaults). The plumbing's own settings (SERVICE_NAME, BROKER_URL, RUN_RELAY,
RUN_CONSUMER, LOG_LEVEL) are read by app/platform/config.py.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=SERVICE_DIR / ".env", extra="ignore")

    # Database: only the outbox and the processed_events inbox (compose generation-db, 5438)
    database_url: str = "postgresql+psycopg://generation:generation@localhost:5438/generation"
    test_database_url: str = (
        "postgresql+psycopg://generation:generation@localhost:5438/generation_test"
    )

    # The kill switch: false fails every request at once with code "provider".
    generation_enabled: bool = True
    # The built-in fake model (app/llm.py, FakeLLM): no key, no network.
    generation_fake: bool = True
    # An OpenAI-compatible API: POST {base_url}/chat/completions with a bearer key.
    generation_base_url: str = ""
    generation_api_key: str = ""
    generation_model: str = ""
    generation_check_model: str = ""  # empty: same as generation_model
    generation_fallback_model: str = ""  # tried once if a call to the main model fails
    generation_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
