"""Alpha Vantage collector."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.collectors.base import Bar, MarketDataProvider, QuotePoint
from app.config import get_settings


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha_vantage"
    BASE = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or get_settings().alpha_vantage_api_key

    async def health(self) -> bool:
        return bool(self.api_key)

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        if not self.api_key:
            return []
        function = "TIME_SERIES_DAILY" if timeframe == "1d" else "TIME_SERIES_INTRADAY"
        params: dict = {"function": function, "symbol": ticker, "apikey": self.api_key, "outputsize": "compact"}
        if function == "TIME_SERIES_INTRADAY":
            params["interval"] = "60min" if timeframe == "1h" else "5min"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
        key = next((k for k in data if "Time Series" in k), None)
        if not key:
            return []
        series = data[key]
        bars: list[Bar] = []
        for ts_str, row in list(series.items())[:limit]:
            ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
            bars.append(
                Bar(
                    ticker=ticker,
                    timeframe=timeframe,
                    ts=ts,
                    open=float(row["1. open"]),
                    high=float(row["2. high"]),
                    low=float(row["3. low"]),
                    close=float(row["4. close"]),
                    volume=float(row.get("5. volume", 0)),
                    source=self.name,
                )
            )
        return list(reversed(bars))

    async def fetch_quote(self, series_code: str) -> QuotePoint | None:
        bars = await self.fetch_bars(series_code, limit=1)
        if not bars:
            return None
        b = bars[-1]
        return QuotePoint(series_code=series_code, ts=b.ts, value=b.close, source=self.name)
