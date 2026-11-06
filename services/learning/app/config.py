"""Settings for the Learning service, read from the environment (docker-compose.yml sets
them). The plumbing's own settings (SERVICE_NAME, GATEWAY_KEY, BROKER_URL, RUN_*) are read
by app/platform/config.py."""

import os
from dataclasses import dataclass
from functools import lru_cache

LOCAL_DATABASE = "postgresql+psycopg://learning:learning@localhost:5435/learning"
LOCAL_TEST_DATABASE = "postgresql+psycopg://learning:learning@localhost:5435/learning_test"


@dataclass(frozen=True)
class Settings:
    database_url: str
    test_database_url: str
    # The seed learner whose circles the seed fills in (Identity's SEED_USER_EMAIL).
    seed_user_email: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", LOCAL_DATABASE),
        test_database_url=os.environ.get("TEST_DATABASE_URL", LOCAL_TEST_DATABASE),
        seed_user_email=os.environ.get("SEED_USER_EMAIL", "newcomer@sgjio.example.com"),
    )
