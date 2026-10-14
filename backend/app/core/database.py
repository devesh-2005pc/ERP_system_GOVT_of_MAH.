"""
SQLAlchemy engine & session management.

Uses DATABASE_URL from settings. Works unmodified with:
  - sqlite:///./data/mudranalaya.db   (development, zero setup)
  - postgresql+psycopg2://user:pass@host:5432/dbname   (production/office server)

For PostgreSQL, row-level locking (SELECT ... FOR UPDATE) is used on the
inventory hot path (see services/inventory.py) to make concurrent stock
transactions safe. SQLite is used only for local dev/tests; it serializes
writes at the file level, which is sufficient for the automated tests here
but PostgreSQL is REQUIRED for real multi-workstation office deployment.
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import get_settings

settings = get_settings()

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    if db_path not in (":memory:",):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Context manager for use outside request handlers (scripts, background jobs)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
