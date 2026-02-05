"""
Database configuration and session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings

# Reduce worst-case startup/readiness delays when the DB host is unreachable.
# (psycopg2 honors connect_timeout in seconds)
_connect_args = {}
if str(getattr(settings, "DATABASE_URL", "")).startswith(("postgresql://", "postgres://")):
    _connect_args = {"connect_timeout": 5}

# Create engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,  # Verify connections before use
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """Async dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
