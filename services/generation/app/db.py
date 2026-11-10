"""Database engine, session factory and the declarative base for Generation's outbox and
inbox."""

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings
from app.platform.config import configure, get_config

# The queue is "<SERVICE_NAME>.events" and the producer field is SERVICE_NAME; compose
# sets it, and a run on the host without it still behaves as "generation".
if get_config().service_name == "unknown":
    configure(service_name="generation")

# Predictable constraint names, as in every SGJio service.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
