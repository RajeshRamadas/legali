from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from . import config

def _normalize_url(url: str) -> str:
    # Accept plain postgresql:// URLs (as docker-compose sets) and use the psycopg 3 driver.
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url

def _engine_options(url: str) -> dict:
    if url.startswith("sqlite"):
        # Used by the test suite: one shared in-memory database across threads.
        return {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    return {"pool_pre_ping": True}

engine = create_engine(_normalize_url(config.DATABASE_URL), **_engine_options(config.DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
