"""Synchronous SQLAlchemy engine and session factory."""

from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings

if not all(
    [settings.db_host, settings.db_name, settings.db_user, settings.db_password]
):
    raise RuntimeError("Supabase Postgres environment variables are missing.")

# Use SSL only when explicitly required (e.g., Supabase). Local Docker/Postgres usually skips it.
if settings.db_host and settings.db_host not in {"localhost", "127.0.0.1"}:
    ssl_suffix = "?sslmode=require"
else:
    ssl_suffix = ""

DATABASE_URL = (
    f"postgresql+psycopg2://{settings.db_user}:{settings.db_password}"
    f"@{settings.db_host}:{settings.db_port}/{settings.db_name}{ssl_suffix}"
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a synchronous SQLAlchemy session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
