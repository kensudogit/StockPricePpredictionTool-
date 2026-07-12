"""Commercial / exchange data adapters (stubs for JPX / QUICK / Bloomberg).

These require institutional contracts. Wire credentials when available.
"""

from __future__ import annotations

from typing import Any

from app.collectors.base import Bar, MarketDataProvider


class JpxDataProvider(MarketDataProvider):
    """JPX Data Cloud / TSE feed adapter placeholder."""

    name = "jpx"

    async def health(self) -> bool:
        return False

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        return []

    async def fetch_order_book(self, ticker: str) -> dict[str, Any]:
        return {"bids": [], "asks": [], "source": self.name, "note": "Requires JPX subscription"}


class QuickProvider(MarketDataProvider):
    """QUICK commercial market data adapter placeholder."""

    name = "quick"

    async def health(self) -> bool:
        return False

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        return []


class BloombergProvider(MarketDataProvider):
    """Bloomberg API (BLPAPI / Data License) adapter placeholder."""

    name = "bloomberg"

    async def health(self) -> bool:
        return False

    async def fetch_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> list[Bar]:
        return []
