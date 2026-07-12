"""信用残・空売り残高 ingestion helpers.

Public free feeds are limited for Japanese margin/short data.
Prefer JPX / QUICK when licensed; this module stores provided payloads.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MarginShort
from app.services.ingestion import DataIngestionService


class MarginShortService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.ingestion = DataIngestionService(db)

    async def upsert(
        self,
        ticker: str,
        as_of: date,
        *,
        margin_buy: float | None = None,
        margin_sell: float | None = None,
        short_interest: float | None = None,
        source: str = "manual",
    ) -> dict:
        symbol = await self.ingestion.ensure_symbol(ticker)
        stmt = (
            insert(MarginShort)
            .values(
                symbol_id=symbol.id,
                as_of_date=as_of,
                margin_buy=Decimal(str(margin_buy)) if margin_buy is not None else None,
                margin_sell=Decimal(str(margin_sell)) if margin_sell is not None else None,
                short_interest=Decimal(str(short_interest)) if short_interest is not None else None,
                source=source,
            )
            .on_conflict_do_update(
                index_elements=["symbol_id", "as_of_date", "source"],
                set_={
                    "margin_buy": Decimal(str(margin_buy)) if margin_buy is not None else None,
                    "margin_sell": Decimal(str(margin_sell)) if margin_sell is not None else None,
                    "short_interest": Decimal(str(short_interest)) if short_interest is not None else None,
                },
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return {"ticker": ticker, "as_of": as_of.isoformat(), "source": source}
