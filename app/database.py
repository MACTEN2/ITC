"""Database connection and session management for the ITC simulator.

Uses SQLite for zero-config local persistence and exposes a FastAPI-compatible
dependency (`get_db`) for per-request session handling.
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Anchored to the project root (not the process's current working directory)
# so `itc_database.db` always lands in the same place regardless of where
# `uvicorn` or `pytest` is launched from.
BASE_DIR = Path(__file__).resolve().parent.parent
SQLALCHEMY_DATABASE_URL = f"sqlite:///{BASE_DIR / 'itc_database.db'}"

# check_same_thread=False is required because SQLite by default only allows
# a connection to be used by the thread that created it, but FastAPI can
# handle a single request across multiple threads.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and guarantees closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create every table registered on `Base.metadata` if it doesn't exist yet.

    Idempotent: safe to call on every app startup. This is what makes
    `itc_database.db` materialize automatically on first run with no manual
    migration step -- SQLAlchemy's `create_all` only issues CREATE TABLE for
    tables that aren't already present.
    """
    Base.metadata.create_all(bind=engine)
