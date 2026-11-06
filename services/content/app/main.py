"""STUB (step 0): health endpoints only, so the compose stack can be brought up and checked.
The content service builder replaces this file with the real service."""

import os

from fastapi import FastAPI, Response
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
app = FastAPI(title="SGJio content (stub)")


@app.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def ready(response: Response) -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ok"}
