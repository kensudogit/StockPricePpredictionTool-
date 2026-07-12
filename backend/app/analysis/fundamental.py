"""Fundamental metrics: PER / PBR / ROE / ROA / EPS / BPS / margins."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Fundamental, Symbol
from app.services.ingestion import DataIngestionService

logger = logging.getLogger("stockai.fundamental")


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _empty_fundamentals(ticker: str, note: str) -> dict[str, Any]:
    return {
        "per": None,
        "pbr": None,
        "roe": None,
        "roa": None,
        "eps": None,
        "bps": None,
        "operating_margin": None,
        "equity_ratio": None,
        "market_cap": None,
        "source": "yahoo",
        "meta": {"ticker": ticker, "note": note},
    }


def fetch_fundamentals_yahoo(ticker: str) -> dict[str, Any]:
    """Best-effort Yahoo fundamentals. Never raises — returns nulls on failure."""
    info: dict[str, Any] = {}
    try:
        t = yf.Ticker(ticker)
        try:
            info = dict(t.info or {})
        except Exception as e:  # noqa: BLE001 — Yahoo often returns empty HTML / JSON errors
            logger.warning("ticker.info failed for %s: %s", ticker, e)
            info = {}
        if not info:
            try:
                fi = getattr(t, "fast_info", None)
                if fi:
                    info = {
                        "marketCap": getattr(fi, "market_cap", None),
                        "currency": getattr(fi, "currency", None),
                        "previousClose": getattr(fi, "previous_close", None),
                    }
            except Exception as e:  # noqa: BLE001
                logger.warning("fast_info failed for %s: %s", ticker, e)
    except Exception as e:  # noqa: BLE001
        logger.warning("yfinance Ticker failed for %s: %s", ticker, e)
        return _empty_fundamentals(ticker, str(e))

    if not info:
        return _empty_fundamentals(ticker, "yahoo returned empty info")

    per = _safe_float(info.get("trailingPE") or info.get("forwardPE"))
    pbr = _safe_float(info.get("priceToBook"))
    roe = _safe_float(info.get("returnOnEquity"))
    roa = _safe_float(info.get("returnOnAssets"))
    eps = _safe_float(info.get("trailingEps") or info.get("forwardEps"))
    book = _safe_float(info.get("bookValue"))
    op_margin = _safe_float(info.get("operatingMargins"))
    de = _safe_float(info.get("debtToEquity"))
    equity_ratio = None
    if de is not None and de >= 0:
        equity_ratio = 1.0 / (1.0 + de / 100.0)
    return {
        "per": per,
        "pbr": pbr,
        "roe": roe,
        "roa": roa,
        "eps": eps,
        "bps": book,
        "operating_margin": op_margin,
        "equity_ratio": equity_ratio,
        "market_cap": _safe_float(info.get("marketCap")),
        "source": "yahoo",
        "meta": {
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "currency": info.get("currency"),
            "name": info.get("shortName") or info.get("longName"),
        },
    }


class FundamentalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.ingestion = DataIngestionService(db)

    async def ingest(self, ticker: str) -> dict:
        import asyncio

        data = await asyncio.to_thread(fetch_fundamentals_yahoo, ticker)
        name = (data.get("meta") or {}).get("name") or (data.get("meta") or {}).get("industry")
        symbol = await self.ingestion.ensure_symbol(ticker, name=name)
        rec = Fundamental(
            symbol_id=symbol.id,
            as_of_date=date.today(),
            per=Decimal(str(data["per"])) if data["per"] is not None else None,
            pbr=Decimal(str(data["pbr"])) if data["pbr"] is not None else None,
            roe=Decimal(str(data["roe"])) if data["roe"] is not None else None,
            roa=Decimal(str(data["roa"])) if data["roa"] is not None else None,
            eps=Decimal(str(data["eps"])) if data["eps"] is not None else None,
            bps=Decimal(str(data["bps"])) if data["bps"] is not None else None,
            operating_margin=Decimal(str(data["operating_margin"])) if data["operating_margin"] is not None else None,
            equity_ratio=Decimal(str(data["equity_ratio"])) if data["equity_ratio"] is not None else None,
            market_cap=Decimal(str(data["market_cap"])) if data["market_cap"] is not None else None,
            source=data["source"],
            meta=data.get("meta") or {},
        )
        existing = (
            await self.db.execute(
                select(Fundamental).where(
                    Fundamental.symbol_id == symbol.id,
                    Fundamental.as_of_date == date.today(),
                    Fundamental.source == data["source"],
                )
            )
        ).scalar_one_or_none()
        if existing:
            for k in ("per", "pbr", "roe", "roa", "eps", "bps", "operating_margin", "equity_ratio", "market_cap"):
                setattr(existing, k, getattr(rec, k))
            existing.meta = rec.meta
            await self.db.commit()
            await self.db.refresh(existing)
            return {"ticker": ticker, **data, "id": existing.id}
        self.db.add(rec)
        await self.db.commit()
        await self.db.refresh(rec)
        return {"ticker": ticker, **data, "id": rec.id}

    async def latest(self, ticker: str) -> dict | None:
        sym = (await self.db.execute(select(Symbol).where(Symbol.ticker == ticker))).scalar_one_or_none()
        if not sym:
            return None
        row = (
            await self.db.execute(
                select(Fundamental)
                .where(Fundamental.symbol_id == sym.id)
                .order_by(Fundamental.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            return None
        return {
            "ticker": ticker,
            "as_of_date": row.as_of_date.isoformat(),
            "per": float(row.per) if row.per is not None else None,
            "pbr": float(row.pbr) if row.pbr is not None else None,
            "roe": float(row.roe) if row.roe is not None else None,
            "roa": float(row.roa) if row.roa is not None else None,
            "eps": float(row.eps) if row.eps is not None else None,
            "bps": float(row.bps) if row.bps is not None else None,
            "operating_margin": float(row.operating_margin) if row.operating_margin is not None else None,
            "equity_ratio": float(row.equity_ratio) if row.equity_ratio is not None else None,
            "market_cap": float(row.market_cap) if row.market_cap is not None else None,
            "source": row.source,
            "meta": row.meta,
        }
