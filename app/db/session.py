"""
Async SQLAlchemy session factory with connection pooling and retry logic.
"""

import logging
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Async engine with connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # Verify connections before use
    echo=settings.DEBUG,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncSession:
    """
    Dependency that provides a database session.
    Ensures proper cleanup on exit.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables (for development). Use Alembic in production."""
    from app.db.base import Base
    # Import all models so they register with Base.metadata
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


async def close_db():
    """Dispose of the engine connection pool."""
    await engine.dispose()
    logger.info("Database connection pool closed")
