"""SGJio Learning service: lesson runs, progress, review, the aptitude quiz and lesson
insights (docs/architecture/detailed-plan.md, section 2.3).

Run locally with:  uvicorn app.main:app --reload --port 8003
Swagger (direct, bypassing the gateway): http://localhost:8003/docs

The event consumer runs as a background thread in this process (RUN_CONSUMER). Learning
publishes nothing, so it has no outbox relay.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.consumers import consumer
from app.db import SessionLocal
from app.platform.lifespan import background_workers, install_platform
from app.platform.logging import configure_logging
from app.routers import aptitude, insights, lessons, progress, review

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with background_workers(SessionLocal, relay=False, consumers=[consumer]):
        yield


app = FastAPI(
    title="SGJio learning",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)
install_platform(app, SessionLocal)

# Paths are the monolith's, unchanged: the gateway forwards /api/... as it receives it.
app.include_router(progress.router, prefix="/api", tags=["Progress"])
app.include_router(lessons.router, prefix="/api", tags=["Lessons (learners)"])
app.include_router(review.router, prefix="/api", tags=["Review (learners)"])
app.include_router(aptitude.router, prefix="/api", tags=["Aptitude quiz"])
app.include_router(insights.router, prefix="/api/admin", tags=["Admin: lesson insights"])
