from collections.abc import AsyncGenerator
import os
import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings, to_async_database_url


def _build_ssl_connect_args(database_url: str) -> dict:
    """Railway / managed Postgres often presents a chain Python rejects by default."""
    markers = ("railway", "rlwy", "amazonaws.com", "neon.tech", "supabase", "render.com")
    force = os.getenv("DATABASE_SSL", "").lower() in {"1", "true", "require"}
    needs_ssl = force or any(m in database_url for m in markers)
    if not needs_ssl:
        return {}

    # Prefer insecure SSL for managed proxies with self-signed intermediates.
    # Set DATABASE_SSL_VERIFY=true to enforce full verification.
    verify = os.getenv("DATABASE_SSL_VERIFY", "false").lower() in {"1", "true", "yes"}
    if verify:
        return {"ssl": True}

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return {"ssl": ctx}


settings = get_settings()
_database_url = to_async_database_url(settings.database_url)
_connect_args = _build_ssl_connect_args(_database_url)

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
