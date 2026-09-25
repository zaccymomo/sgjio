from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Used by the front ends and by deployment checks. Also confirms the database is up."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
