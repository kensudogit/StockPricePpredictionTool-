"""Stooq CSV collector — works well from cloud IPs where Yahoo is blocked."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone

import httpx

from app.collectors.base import Bar, MarketDataProvider, QuotePoint

logger = logging.getLogger("stockai.stooq")


def to_stooq_symbol(ticker: str) -> str | None:
    t = ticker.strip()
    if t.endswith(".T"):
        return f"{t[:-2].lower()}.jp"
    if t.endswith(".JP"):
        return t.lower()
    # US common
    if "." not in t and not t.startswith("^"):
        return f"{t.lower()}.us"
    # Indices on Stooq
    index_map = {
        "^N225": "^nkx",
        "^GSPC": "^spx",
        "^IXIC": "^ndq",
        "^VIX": "^vix",
        "^TNX": "^tnx",
        "USDJPY=X": "jpyusd",  # note: inverted pair naming differs; skip if odd
        "CL=F": "cl.f",
    }
    if t in index_map:
        return index_map[t]
    return None


class StooqProvider(MarketDataProvider):
    name = "stooq"

    async def health(self) -> bool:
        return True

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        if timeframe not in {"1d", "1wk"}:
            # Stooq free CSV is daily-oriented
            timeframe = "1d"
        symbol = to_stooq_symbol(ticker)
        if not symbol:
            return []
        interval = "d" if timeframe == "1d" else "w"
        url = f"https://stooq.com/q/d/l/?s={symbol}&i={interval}"
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "StockAI/1.0"})
                resp.raise_for_status()
                text = resp.text.strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("stooq fetch failed %s: %s", ticker, e)
            return []

        if not text or text.lower().startswith("<!doctype") or "No data" in text:
            return []

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return []

        bars: list[Bar] = []
        for row in rows[-limit:]:
            try:
                # Stooq columns: Date,Open,High,Low,Close,Volume
                date_s = row.get("Date") or row.get("date")
                if not date_s:
                    continue
                ts = datetime.strptime(date_s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                bars.append(
                    Bar(
                        ticker=ticker,
                        timeframe=timeframe,
                        ts=ts,
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=float(row.get("Volume") or 0),
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
