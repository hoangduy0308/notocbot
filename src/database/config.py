"""
Database configuration and connection setup.
Supports async SQLAlchemy with PostgreSQL.
"""

import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import MetaData

# Load database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

# Convert postgres:// to postgresql+psycopg:// for async support
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debug logging
    future=True,
    pool_pre_ping=True,  # Validate connections before using
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Metadata for migrations
metadata = MetaData()


async def get_session():
    """Get async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize database (create all tables)."""
    from src.database.models import Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


__all__ = ["engine", "AsyncSessionLocal", "get_session", "init_db", "DATABASE_URL"]
