"""SGJio Identity: accounts, sessions, credentials, administrators, profile, introduction.

Run locally with:  uvicorn app.main:app --reload --port 8001
Interactive API docs: http://localhost:8001/docs (direct, bypassing the gateway)

Every public path is the monolith's, unchanged; the gateway sends /api/auth/*,
/api/admin/auth/*, /api/admin/admins*, /api/admin/ping, /api/profile* and /api/intro/*
here. /internal/auth/{app,admin} answers the gateway's session checks. The outbox relay
runs as a background thread for the life of the process; Identity consumes no events.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import SessionLocal
from app.models import AuthScope
from app.platform.lifespan import background_workers, install_platform
from app.platform.logging import configure_logging
from app.routers import admin, internal, onboarding, profile
from app.routers.auth import build_auth_router

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with background_workers(SessionLocal, relay=True, consumers=[]):
        yield


app = FastAPI(
    title="SGJio identity",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
install_platform(app, SessionLocal)

app.include_router(profile.router, prefix="/api", tags=["Profile"])
app.include_router(onboarding.router, prefix="/api", tags=["Onboarding"])
app.include_router(build_auth_router(AuthScope.APP), prefix="/api/auth", tags=["Auth (main app)"])
app.include_router(
    build_auth_router(AuthScope.ADMIN), prefix="/api/admin/auth", tags=["Auth (admin portal)"]
)
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(internal.router)
