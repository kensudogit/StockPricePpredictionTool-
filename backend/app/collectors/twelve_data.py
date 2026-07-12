"""Twelve Data collector."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.collectors.base import Bar, MarketDataProvider, QuotePoint
from app.config import get_settings


class TwelveDataProvider(MarketDataProvider):
    name = "twelve_data"
    BASE = "https://api.twelvedata.com"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or get_settings().twelve_data_api_key

    async def health(self) -> bool:
        return bool(self.api_key)

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        if not self.api_key:
            return []
        interval = {"1d": "1day", "1h": "1h", "5m": "5min"}.get(timeframe, "1day")
        params = {
            "symbol": ticker,
            "interval": interval,
            "outputsize": limit,
            "apikey": self.api_key,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self.BASE}/time_series", params=params)
            resp.raise_for_status()
            data = resp.json()
        values = data.get("values") or []
        bars: list[Bar] = []
        for row in reversed(values):
            ts = datetime.fromisoformat(row["datetime"]).replace(tzinfo=timezone.utc)
            bars.append(
                Bar(
                    ticker=ticker,
                    timeframe=timeframe,
                    ts=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                    source=self.name,
                )
            )
        return bars

    async def fetch_quote(self, series_code: str) -> QuotePoint | None:
        bars = await self.fetch_bars(series_code, limit=1)
        if not bars:
            return None
        b = bars[-1]
        return QuotePoint(series_code=series_code, ts=b.ts, value=b.close, source=self.name)
