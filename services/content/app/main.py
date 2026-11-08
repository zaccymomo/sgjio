"""The Content service: authoring and publishing (topics, lessons, versions, media, reported
problems, the aptitude question bank). See docs/architecture/detailed-plan.md, section 2.2.

    uvicorn app.main:app --reload --port 8002      Swagger at http://localhost:8002/docs

Every route keeps the monolith's path under /api; the gateway sends Content its share
(services/gateway/templates/gateway.conf.template). The outbox relay and the
identity.user.deleted consumer run as background threads (RUN_RELAY, RUN_CONSUMER).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.consumers import build_consumer
from app.db import SessionLocal
from app.platform.lifespan import background_workers, install_platform
from app.platform.logging import configure_logging
from app.routers import admin, media, reports

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with background_workers(SessionLocal, relay=True, consumers=[build_consumer()]):
        yield


app = FastAPI(
    title="SGJio content",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)
install_platform(app, SessionLocal)

app.include_router(media.router, prefix="/api", tags=["Media"])
app.include_router(reports.router, prefix="/api", tags=["Reported problems (learners)"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
