"""Ensure DB schema exists (Railway Postgres does not run docker init.sql)."""

from __future__ import annotations

import logging

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.session import Base

logger = logging.getLogger("stockai.bootstrap")

# Register metadata
import app.models  # noqa: E402, F401
from app.models import Symbol  # noqa: E402

SEED_SYMBOLS = [
    ("7203.T", "Toyota Motor", "TSE", "equity", "JPY"),
    ("6758.T", "Sony Group", "TSE", "equity", "JPY"),
    ("9984.T", "SoftBank Group", "TSE", "equity", "JPY"),
    ("^N225", "Nikkei 225", "INDEX", "index", "JPY"),
    ("^TOPX", "TOPIX", "INDEX", "index", "JPY"),
    ("^GSPC", "S&P 500", "INDEX", "index", "USD"),
    ("^IXIC", "NASDAQ Composite", "INDEX", "index", "USD"),
    ("^VIX", "CBOE Volatility Index", "INDEX", "index", "USD"),
    ("USDJPY=X", "USD/JPY", "FX", "fx", "JPY"),
    ("CL=F", "Crude Oil WTI", "CME", "commodity", "USD"),
    ("^TNX", "US 10Y Treasury Yield", "INDEX", "rate", "USD"),
]


async def init_database(engine: AsyncEngine) -> None:
    """Create extensions, tables, and seed symbols if missing."""
    for ext in ("uuid-ossp", "pg_trgm", "vector"):
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{ext}"'))
        except Exception as e:  # noqa: BLE001
            logger.warning("extension %s skipped: %s", ext, e)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    for sql in (
        "ALTER TABLE positions ADD COLUMN IF NOT EXISTS stop_loss NUMERIC(18, 6)",
        "ALTER TABLE positions ADD COLUMN IF NOT EXISTS take_profit NUMERIC(18, 6)",
        "ALTER TABLE positions ADD COLUMN IF NOT EXISTS leverage NUMERIC(8, 2) DEFAULT 1",
        "ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS embedding vector(384)",
    ):
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql))
        except Exception as e:  # noqa: BLE001
            logger.warning("DDL skipped (%s): %s", sql[:48], e)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        count = (await session.execute(select(func.count()).select_from(Symbol))).scalar_one()
        if count == 0:
            for ticker, name, exchange, asset_type, currency in SEED_SYMBOLS:
                session.add(
                    Symbol(
                        ticker=ticker,
                        name=name,
                        exchange=exchange,
                        asset_type=asset_type,
                        currency=currency,
                    )
                )
            await session.commit()
            logger.info("seeded %s symbols", len(SEED_SYMBOLS))
        else:
            logger.info("symbols already present: %s", count)
