"""Identity's settings, read from environment variables or services/identity/.env.

docker-compose.yml sets every one of them for the container. The plumbing's own settings
(SERVICE_NAME, GATEWAY_KEY, BROKER_URL, RUN_RELAY, RUN_CONSUMER, LOG_LEVEL) are read by
app/platform/config.py.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=SERVICE_DIR / ".env", extra="ignore")

    # Database (host ports from docker-compose.yml: identity-db is 5433)
    database_url: str = "postgresql+psycopg://identity:identity@localhost:5433/identity"
    test_database_url: str = "postgresql+psycopg://identity:identity@localhost:5433/identity_test"

    # Front-end addresses, used to build links in emails
    web_url: str = "http://localhost:5173"
    admin_url: str = "http://localhost:5174"

    # Sessions and sign-in. Defaults are the team's proposed values (docs/decisions.md).
    cookie_secure: bool = False
    app_session_days: int = 7
    admin_session_hours: int = 8
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    # 15 on the microservices branch (5 in the monolith): the email is now sent
    # asynchronously by Notification, so the link needs more time to arrive.
    reset_token_minutes: int = 15

    # Inviting administrators from the portal (SCRUM-81). An invite arrives whenever it
    # arrives, so its link lasts longer than a reset link someone has just asked for.
    invite_link_hours: int = 72
    # Adding an administrator outside this email domain asks for confirmation. Empty: no check.
    admin_email_domain: str = "sgjio.example.com"

    # Sign in with Google (SCRUM-92): the Firebase project whose ID tokens are accepted.
    # Empty switches Google sign-in off.
    firebase_project_id: str = ""

    # Seed accounts for local development
    seed_admin_email: str = "admin@sgjio.example.com"
    seed_admin_password: str = "AdminPass123"
    seed_user_email: str = "newcomer@sgjio.example.com"
    seed_user_password: str = "UserPass123"


@lru_cache
def get_settings() -> Settings:
    return Settings()
