"""SGJio API entry point.

Run locally with:  uvicorn app.main:app --reload
Interactive API docs: http://localhost:8000/api/docs
"""

import logging

from fastapi import FastAPI

from app.models import AuthScope
from app.routers import admin, aptitude, health, lessons, media, profile, progress, review
from app.routers.auth import build_auth_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="SGJio API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

# Every route lives under /api. In development each front end's Vite server forwards
# /api to this app, so the browser sees one origin and cookies just work (no CORS).
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(progress.router, prefix="/api", tags=["Progress"])
app.include_router(profile.router, prefix="/api", tags=["Profile"])
app.include_router(media.router, prefix="/api", tags=["Media"])
app.include_router(lessons.router, prefix="/api", tags=["Lessons (learners)"])
app.include_router(review.router, prefix="/api", tags=["Review (learners)"])
app.include_router(aptitude.router, prefix="/api", tags=["Aptitude quiz"])
app.include_router(build_auth_router(AuthScope.APP), prefix="/api/auth", tags=["Auth (main app)"])
app.include_router(
    build_auth_router(AuthScope.ADMIN), prefix="/api/admin/auth", tags=["Auth (admin portal)"]
)
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
