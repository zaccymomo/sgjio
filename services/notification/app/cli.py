"""STUB (step 0): `python -m app.cli health` checks the database and the broker, for the
compose healthcheck. The notification builder keeps the command and adds the rest."""

import os
import sys

import pika
from sqlalchemy import create_engine, text


def health() -> int:
    with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
        connection.execute(text("SELECT 1"))
    params = pika.URLParameters(os.environ["BROKER_URL"])
    params.socket_timeout = 5
    pika.BlockingConnection(params).close()
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["health"]:
        sys.exit("usage: python -m app.cli health")
    sys.exit(health())
