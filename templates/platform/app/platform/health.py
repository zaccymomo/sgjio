"""/health/live (the process answers) and /health/ready (and its database answers).

    app.include_router(health_router(SessionLocal))

Readiness does not check the broker: the relay and consumer retry on their own, and the
API still serves requests while the broker is down.
"""

from collections.abc import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session


def health_router(session_factory: Callable[[], Session]) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["Health"])

    @router.get("/live")
    def live() -> dict:
        return {"status": "ok"}

    @router.get("/ready")
    def ready():
        try:
            with session_factory() as session:
                session.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok"}

    return router
