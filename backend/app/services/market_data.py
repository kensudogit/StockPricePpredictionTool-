"""Shared helpers to load OHLCV into DataFrames."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MarketBar, Symbol


async def load_bars_df(
    db: AsyncSession,
    ticker: str,
    timeframe: str = "1d",
    limit: int = 300,
) -> pd.DataFrame:
    sym = (await db.execute(select(Symbol).where(Symbol.ticker == ticker))).scalar_one_or_none()
    if not sym:
        return pd.DataFrame()
    rows = (
        await db.execute(
            select(MarketBar)
            .where(MarketBar.symbol_id == sym.id, MarketBar.timeframe == timeframe)
            .order_by(MarketBar.ts.desc())
            .limit(limit)
        )
    ).scalars().all()
    if not rows:
        return pd.DataFrame()
    data = [
        {
            "ts": r.ts,
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": float(r.volume or 0),
        }
        for r in reversed(rows)
    ]
    return pd.DataFrame(data)


async def get_symbol_id(db: AsyncSession, ticker: str) -> int | None:
    sym = (await db.execute(select(Symbol).where(Symbol.ticker == ticker))).scalar_one_or_none()
    return sym.id if sym else None
