"""Market data ingestion service."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.registry import MACRO_SERIES, get_primary_provider, get_providers
from app.models import MacroSeries, MarketBar, Symbol


class DataIngestionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_symbol(self, ticker: str, **kwargs) -> Symbol:
        result = await self.db.execute(select(Symbol).where(Symbol.ticker == ticker))
        symbol = result.scalar_one_or_none()
        if symbol:
            return symbol
        symbol = Symbol(ticker=ticker, **kwargs)
        self.db.add(symbol)
        await self.db.flush()
        return symbol

    async def ingest_bars(self, ticker: str, timeframe: str = "1d", limit: int = 100) -> dict:
        providers = get_providers()
        bars = []
        provider = providers[0]
        ordered = sorted(
            providers,
            key=lambda p: (
                0 if p.name == "yahoo" else 1 if (ticker.endswith(".T") and p.name == "stooq") else 2
            ),
        )
        for p in ordered:
            try:
                bars = await p.fetch_bars(ticker, timeframe=timeframe, limit=limit)
            except Exception:
                bars = []
            if bars:
                provider = p
                break
        symbol = await self.ensure_symbol(ticker)
        upserted = 0
        for bar in bars:
            stmt = (
                insert(MarketBar)
                .values(
                    symbol_id=symbol.id,
                    timeframe=bar.timeframe,
                    ts=bar.ts,
                    open=Decimal(str(bar.open)),
                    high=Decimal(str(bar.high)),
                    low=Decimal(str(bar.low)),
                    close=Decimal(str(bar.close)),
                    volume=Decimal(str(bar.volume)),
                    source=bar.source,
                )
                .on_conflict_do_update(
                    index_elements=["symbol_id", "timeframe", "ts"],
                    set_={
                        "open": Decimal(str(bar.open)),
                        "high": Decimal(str(bar.high)),
                        "low": Decimal(str(bar.low)),
                        "close": Decimal(str(bar.close)),
                        "volume": Decimal(str(bar.volume)),
                        "source": bar.source,
                    },
                )
            )
            await self.db.execute(stmt)
            upserted += 1
        await self.db.commit()
        return {"ticker": ticker, "source": provider.name, "bars": upserted}

    async def ingest_macro(self) -> dict:
        provider = get_primary_provider()
        saved = 0
        details = {}
        for code, ticker in MACRO_SERIES.items():
            quote = await provider.fetch_quote(ticker)
            if not quote:
                continue
            stmt = (
                insert(MacroSeries)
                .values(
                    series_code=code,
                    ts=quote.ts,
                    value=Decimal(str(quote.value)),
                    source=quote.source,
                )
                .on_conflict_do_update(
                    index_elements=["series_code", "ts"],
                    set_={"value": Decimal(str(quote.value)), "source": quote.source},
                )
            )
            await self.db.execute(stmt)
            saved += 1
            details[code] = float(quote.value)
        await self.db.commit()
        return {"saved": saved, "values": details}

    async def provider_status(self) -> list[dict]:
        status = []
        for p in get_providers():
            ok = await p.health()
            status.append({"name": p.name, "available": ok})
        return status
