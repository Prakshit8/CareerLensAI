"""SQLite engine, declarative base, and request-scoped sessions."""

from collections.abc import Generator
from pathlib import Path
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import settings


if settings.database_url.startswith("sqlite:///"):
    database_path = settings.database_url.removeprefix("sqlite:///")
    if not database_path.startswith(":memory:"):
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(
    dbapi_connection: sqlite3.Connection, connection_record: object
) -> None:
    """Enable SQLite foreign-key enforcement for each connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    """Base type for application database models."""


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a session and always close it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
