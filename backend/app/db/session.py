from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings, to_async_database_url

settings = get_settings()

# Railway/Heroku inject DATABASE_URL as postgres:// or postgresql:// (psycopg2).
# Always force asyncpg for create_async_engine.
_database_url = to_async_database_url(settings.database_url)

engine = create_async_engine(
    _database_url,
    echo=False,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
