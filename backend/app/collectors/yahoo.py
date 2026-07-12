"""Yahoo Finance collector — research / prototype use only.

Uses the chart JSON API first (more reliable from cloud hosts),
then falls back to yfinance download/history.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
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

CHART_RANGE = {
    "1m": "1d",
    "5m": "5d",
    "15m": "5d",
    "1h": "1mo",
    "1d": "1y",
    "1wk": "5y",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


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

    async def _fetch_chart_api(self, ticker: str, timeframe: str, limit: int) -> list[Bar]:
        interval = TIMEFRAME_MAP.get(timeframe, ("1d", "1y"))[0]
        # Prefer range sized for limit so Railway gets enough bars for indicators
        if timeframe == "1d":
            chart_range = "2y" if limit > 200 else "1y" if limit > 80 else "6mo"
        else:
            chart_range = CHART_RANGE.get(timeframe, "1y")
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            f"?interval={interval}&range={chart_range}"
        )
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": UA, "Accept": "application/json"},
                )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("yahoo chart api failed for %s: %s", ticker, e)
            return []

        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            return []
        block = result[0]
        timestamps = block.get("timestamp") or []
        quote = ((block.get("indicators") or {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        bars: list[Bar] = []
        for i, ts in enumerate(timestamps):
            try:
                c = closes[i] if i < len(closes) else None
                if c is None:
                    continue
                o = opens[i] if i < len(opens) and opens[i] is not None else c
                h = highs[i] if i < len(highs) and highs[i] is not None else c
                l = lows[i] if i < len(lows) and lows[i] is not None else c
                v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0
                bars.append(
                    Bar(
                        ticker=ticker,
                        timeframe=timeframe,
                        ts=datetime.fromtimestamp(ts, tz=timezone.utc),
                        open=float(o),
                        high=float(h),
                        low=float(l),
                        close=float(c),
                        volume=float(v),
                        source=self.name,
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        return bars[-limit:]

    async def _fetch_yfinance(self, ticker: str, timeframe: str, limit: int) -> list[Bar]:
        interval, period = TIMEFRAME_MAP.get(timeframe, ("1d", "1y"))
        try:
            df = await asyncio.to_thread(_download_sync, ticker, period, interval)
        except Exception as e:  # noqa: BLE001
            logger.warning("yahoo download failed for %s: %s", ticker, e)
            df = None
        if df is None or getattr(df, "empty", True):
            try:
                t = yf.Ticker(ticker)
                df = await asyncio.to_thread(
                    lambda: t.history(period=period, interval=interval, auto_adjust=True)
                )
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

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        bars = await self._fetch_chart_api(ticker, timeframe, limit)
        if bars:
            return bars
        return await self._fetch_yfinance(ticker, timeframe, limit)

    async def fetch_quote(self, series_code: str) -> QuotePoint | None:
        bars = await self.fetch_bars(series_code, timeframe="1d", limit=1)
        if not bars:
            return None
        b = bars[-1]
        return QuotePoint(series_code=series_code, ts=b.ts, value=b.close, source=self.name)
