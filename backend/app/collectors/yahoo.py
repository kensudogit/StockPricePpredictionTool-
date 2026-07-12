"""Yahoo Finance collector — research / prototype use only."""

from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf

from app.collectors.base import Bar, MarketDataProvider, QuotePoint

TIMEFRAME_MAP = {
    "1m": ("1m", "1d"),
    "5m": ("5m", "5d"),
    "15m": ("15m", "5d"),
    "1h": ("60m", "1mo"),
    "1d": ("1d", "1y"),
    "1wk": ("1wk", "5y"),
}


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo"

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        interval, period = TIMEFRAME_MAP.get(timeframe, ("1d", "1y"))
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return []
        if hasattr(df.columns, "levels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        bars: list[Bar] = []
        for ts, row in df.tail(limit).iterrows():
            ts_dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            bars.append(
                Bar(
                    ticker=ticker,
                    timeframe=timeframe,
                    ts=ts_dt,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0) or 0),
                    source=self.name,
                )
            )
        return bars

    async def fetch_quote(self, series_code: str) -> QuotePoint | None:
        bars = await self.fetch_bars(series_code, timeframe="1d", limit=1)
        if not bars:
            return None
        b = bars[-1]
        return QuotePoint(series_code=series_code, ts=b.ts, value=b.close, source=self.name)
