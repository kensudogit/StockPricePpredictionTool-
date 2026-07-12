from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings, to_async_database_url

settings = get_settings()
_database_url = to_async_database_url(settings.database_url)

_cloud_markers = ("railway", "rlwy", "amazonaws.com", "neon.tech", "supabase", "render.com")
_needs_ssl = any(m in _database_url for m in _cloud_markers)

_connect_args: dict = {}
if _needs_ssl:
    _connect_args["ssl"] = True

engine = create_async_engine(
    _database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
