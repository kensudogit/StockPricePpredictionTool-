from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class Bar:
    ticker: str
    timeframe: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


@dataclass
class QuotePoint:
    series_code: str
    ts: datetime
    value: float
    source: str


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    async def fetch_bars(
        self,
        ticker: str,
        timeframe: str = "1d",
        limit: int = 100,
    ) -> list[Bar]:
        raise NotImplementedError

    async def fetch_quote(self, series_code: str) -> Optional[QuotePoint]:
        return None

    async def fetch_order_book(self, ticker: str) -> dict[str, Any]:
        return {"bids": [], "asks": [], "source": self.name}

    async def health(self) -> bool:
        return True
