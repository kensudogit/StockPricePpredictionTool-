"""Yahoo Finance collector — research / prototype use only."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import yfinance as yf

from app.collectors.base import Bar, MarketDataProvider, QuotePoint

logger = logging.getLogger("stockai.yahoo")

TIMEFRAME_MAP = {
    "1m": ("1m", "1d"),
    "5m": ("5m", "5d"),
    "15m": ("15m", "5d"),
    "1h": ("60m", "1mo"),
    "1d": ("1d", "1y"),
    "1wk": ("1wk", "5y"),
}


def _download_sync(ticker: str, period: str, interval: str):
    return yf.download(
        ticker,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=True,
        threads=False,
    )


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo"

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        interval, period = TIMEFRAME_MAP.get(timeframe, ("1d", "1y"))
        try:
            df = await asyncio.to_thread(_download_sync, ticker, period, interval)
        except Exception as e:  # noqa: BLE001
            logger.warning("yahoo download failed for %s: %s", ticker, e)
            return []
        if df is None or df.empty:
            # fallback: history()
            try:
                t = yf.Ticker(ticker)
                df = await asyncio.to_thread(lambda: t.history(period=period, interval=interval, auto_adjust=True))
            except Exception as e:  # noqa: BLE001
                logger.warning("yahoo history failed for %s: %s", ticker, e)
                return []
        if df is None or df.empty:
            return []
        if hasattr(df.columns, "levels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        bars: list[Bar] = []
        for ts, row in df.tail(limit).iterrows():
            try:
                ts_dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
                if getattr(ts_dt, "tzinfo", None) is None:
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
                        volume=float(row["Volume"]) if "Volume" in row and row["Volume"] == row["Volume"] else 0.0,
                        source=self.name,
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        return bars

    async def fetch_quote(self, series_code: str) -> QuotePoint | None:
        bars = await self.fetch_bars(series_code, timeframe="1d", limit=1)
        if not bars:
            return None
        b = bars[-1]
        return QuotePoint(series_code=series_code, ts=b.ts, value=b.close, source=self.name)
