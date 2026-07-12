"""Integrated technical + fundamental + news analysis into one scored view."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.integrated_scoring import (
    combine_scores,
    score_fundamentals,
    score_news,
    score_technical,
)
from app.analysis.technical import latest_snapshot
from app.models import NewsArticle, Symbol
from app.services.ingestion import DataIngestionService
from app.services.market_data import load_bars_df

# Re-export pure scorers for convenience
__all__ = [
    "IntegratedAnalysisService",
    "combine_scores",
    "score_fundamentals",
    "score_news",
    "score_technical",
]


class IntegratedAnalysisService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_bars(self, ticker: str, min_rows: int = 40) -> Any:
        df = await load_bars_df(self.db, ticker, limit=200)
        if len(df) < min_rows:
            try:
                await DataIngestionService(self.db).ingest_bars(ticker, timeframe="1d", limit=200)
            except Exception:  # noqa: BLE001
                pass
            df = await load_bars_df(self.db, ticker, limit=200)
        return df

    async def _news_for_ticker(self, ticker: str, limit: int = 12) -> list[dict[str, Any]]:
        sym = (await self.db.execute(select(Symbol).where(Symbol.ticker == ticker))).scalar_one_or_none()
        q = select(NewsArticle).order_by(NewsArticle.published_at.desc()).limit(40)
        rows = (await self.db.execute(q)).scalars().all()
        out: list[dict[str, Any]] = []
        for r in rows:
            if sym and r.symbol_id and r.symbol_id != sym.id:
                continue
            out.append(
                {
                    "id": r.id,
                    "source": r.source,
                    "category": r.category,
                    "title": r.title,
                    "url": r.url,
                    "published_at": r.published_at.isoformat() if r.published_at else None,
                    "sentiment": float(r.sentiment) if r.sentiment is not None else None,
                    "sentiment_label": r.sentiment_label,
                    "summary": r.summary,
                    "symbol_id": r.symbol_id,
                }
            )
        matched = [a for a in out if sym and a.get("symbol_id") == sym.id]
        others = [a for a in out if not (sym and a.get("symbol_id") == sym.id)]
        return (matched + others)[:limit]

    async def run(self, ticker: str, *, collect_news: bool = True) -> dict[str, Any]:
        from app.analysis.fundamental import FundamentalService
        from app.analysis.news import NewsService
        from app.llm.clients import NewsLLMService

        df = await self._ensure_bars(ticker)
        tech_snap: dict[str, Any] = {}
        if not df.empty:
            try:
                tech_snap = latest_snapshot(df)
            except Exception as e:  # noqa: BLE001
                tech_snap = {"trend": "unknown", "error": str(e)}

        fund_svc = FundamentalService(self.db)
        fund = await fund_svc.latest(ticker)
        if not fund:
            try:
                fund = await fund_svc.ingest(ticker)
            except Exception:  # noqa: BLE001
                fund = None

        if collect_news:
            try:
                await NewsService(self.db).collect(ticker)
            except Exception:  # noqa: BLE001
                pass

        articles = await self._news_for_ticker(ticker)
        llm = NewsLLMService()
        for a in articles:
            if a.get("sentiment") is None and a.get("title"):
                try:
                    sent = await llm.sentiment(str(a["title"]))
                    a["sentiment"] = float(sent.get("score", 0))
                    a["sentiment_label"] = sent.get("label")
                except Exception:  # noqa: BLE001
                    pass

        t_score, t_reasons = score_technical(tech_snap)
        f_score, f_reasons = score_fundamentals(fund if isinstance(fund, dict) else None)
        n_score, n_reasons, n_meta = score_news(articles)
        composite, signal, strength = combine_scores(t_score, f_score, n_score)

        summary = (
            f"{ticker}: 統合シグナルは {signal.upper()} "
            f"（スコア {composite:+.2f} · 強度 {strength:.2f}）。"
            f"テクニカル {t_score:+.2f} / ファンダ {f_score:+.2f} / ニュース {n_score:+.2f}。"
        )

        return {
            "ticker": ticker,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "signal": signal,
            "composite_score": composite,
            "strength": strength,
            "weights": {"technical": 0.45, "fundamental": 0.30, "news": 0.25},
            "scores": {
                "technical": t_score,
                "fundamental": f_score,
                "news": n_score,
            },
            "summary": summary,
            "technical": {
                "score": t_score,
                "snapshot": {
                    k: tech_snap.get(k)
                    for k in ("trend", "close", "rsi_14", "macd", "macd_signal", "adx", "atr_14", "sma_20")
                },
                "reasons": t_reasons,
            },
            "fundamental": {
                "score": f_score,
                "metrics": fund,
                "reasons": f_reasons,
            },
            "news": {
                "score": n_score,
                "meta": n_meta,
                "articles": articles[:8],
                "reasons": n_reasons,
            },
            "radar": [
                {"axis": "Technical", "value": round((t_score + 1) / 2 * 100, 1)},
                {"axis": "Fundamental", "value": round((f_score + 1) / 2 * 100, 1)},
                {"axis": "News", "value": round((n_score + 1) / 2 * 100, 1)},
            ],
        }
