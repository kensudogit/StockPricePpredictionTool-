"""Polygon.io collector."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.collectors.base import Bar, MarketDataProvider, QuotePoint
from app.config import get_settings


class PolygonProvider(MarketDataProvider):
    name = "polygon"
    BASE = "https://api.polygon.io"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or get_settings().polygon_api_key

    async def health(self) -> bool:
        return bool(self.api_key)

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        if not self.api_key:
            return []
        mult, span = (1, "day") if timeframe == "1d" else (1, "hour")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=400 if span == "day" else 30)
        url = f"{self.BASE}/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{start}/{end}"
        params = {"adjusted": "true", "sort": "asc", "limit": limit, "apiKey": self.api_key}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results") or []
        return [
            Bar(
                ticker=ticker,
                timeframe=timeframe,
                ts=datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc),
                open=float(r["o"]),
                high=float(r["h"]),
                low=float(r["l"]),
                close=float(r["c"]),
                volume=float(r.get("v", 0)),
                source=self.name,
            )
            for r in results[-limit:]
        ]

    async def fetch_quote(self, series_code: str) -> QuotePoint | None:
        bars = await self.fetch_bars(series_code, limit=1)
        if not bars:
            return None
        b = bars[-1]
        return QuotePoint(series_code=series_code, ts=b.ts, value=b.close, source=self.name)
