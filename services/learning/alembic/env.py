"""STUB (step 0): Alembic environment with no models yet. The service builder replaces it
with one that imports the service's own models (and only those)."""

import os

from alembic import context
from sqlalchemy import create_engine

target_metadata = None


def run_migrations_online() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
