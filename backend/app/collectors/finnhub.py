"""Finnhub collector."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.collectors.base import Bar, MarketDataProvider, QuotePoint
from app.config import get_settings


class FinnhubProvider(MarketDataProvider):
    name = "finnhub"
    BASE = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or get_settings().finnhub_api_key

    async def health(self) -> bool:
        return bool(self.api_key)

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        if not self.api_key:
            return []
        resolution = "D" if timeframe == "1d" else "60"
        end = int(datetime.now(timezone.utc).timestamp())
        start = int((datetime.now(timezone.utc) - timedelta(days=365)).timestamp())
        params = {
            "symbol": ticker,
            "resolution": resolution,
            "from": start,
            "to": end,
            "token": self.api_key,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self.BASE}/stock/candle", params=params)
            resp.raise_for_status()
            data = resp.json()
        if data.get("s") != "ok":
            return []
        bars: list[Bar] = []
        for i in range(len(data["t"])):
            bars.append(
                Bar(
                    ticker=ticker,
                    timeframe=timeframe,
                    ts=datetime.fromtimestamp(data["t"][i], tz=timezone.utc),
                    open=float(data["o"][i]),
                    high=float(data["h"][i]),
                    low=float(data["l"][i]),
                    close=float(data["c"][i]),
                    volume=float(data["v"][i]),
                    source=self.name,
                )
            )
        return bars[-limit:]

    async def fetch_quote(self, series_code: str) -> QuotePoint | None:
        if not self.api_key:
            return None
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.BASE}/quote",
                params={"symbol": series_code, "token": self.api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        if not data.get("c"):
            return None
        return QuotePoint(
            series_code=series_code,
            ts=datetime.now(timezone.utc),
            value=float(data["c"]),
            source=self.name,
        )
