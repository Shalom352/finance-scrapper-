"""
UMOA Banking Intelligence — Database Session Factory

Provides async database sessions via FastAPI dependency injection.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import engine

# Session factory — used throughout the application
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yields an async database session.

    Usage in a router:
        @router.get("/")
        async def my_endpoint(db: AsyncSession = Depends(get_db_session)):
            ...

    The session is automatically committed on success,
    rolled back on exception, and always closed.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
