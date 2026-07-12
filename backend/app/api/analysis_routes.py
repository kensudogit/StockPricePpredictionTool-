"""Extended analysis / ML / DL / RAG / backtest / broker endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.fundamental import FundamentalService
from app.analysis.news import NewsService
from app.analysis.technical import latest_snapshot, series_for_chart
from app.backtest.engine import BacktestService
from app.brokers import get_broker, list_broker_status
from app.brokers.base import BrokerOrderRequest
from app.db.session import get_db
from app.dl.models import DeepLearningService
from app.llm.clients import NewsLLMService
from app.ml.ensemble import MLEnsembleService
from app.models import ChatMessage, NewsArticle, TechnicalSnapshot
from app.rag.store import RAGService
from app.risk.manager import EnhancedRiskManager
from app.services.market_data import get_symbol_id, load_bars_df

router = APIRouter(tags=["analysis"])


class TickerBody(BaseModel):
    ticker: str = Field(..., examples=["7203.T"])


class MLPredictBody(BaseModel):
    ticker: str
    models: list[str] | None = None


class DLPredictBody(BaseModel):
    ticker: str
    model: str = "lstm"  # lstm | gru | transformer | tft
    backend: str = "pytorch"  # pytorch | tensorflow
    epochs: int = 12


class BacktestBody(BaseModel):
    ticker: str
    engine: str = "vectorbt"  # vectorbt | backtrader | zipline | pandas
    fast: int = 10
    slow: int = 30


class NewsAnalyzeBody(BaseModel):
    text: str
    mode: str = "sentiment"  # summarize | ir | earnings | sentiment


class RagIngestBody(BaseModel):
    content: str
    doc_type: str = Field(..., examples=["news", "ir", "earnings", "chat"])
    title: str | None = None
    ticker: str | None = None
    source_ref: str | None = None


class RagQueryBody(BaseModel):
    question: str
    limit: int = 5
    session_id: str | None = None


class BrokerOrderBody(BaseModel):
    ticker: str
    side: str
    quantity: float
    broker: str | None = None
    order_type: str = "market"
    limit_price: float | None = None


class RiskSizeBody(BaseModel):
    equity: float = 10_000_000
    price: float
    stop_loss_pct: float | None = None
    risk_per_trade_pct: float = 0.01


@router.get("/technical/{ticker}")
async def technical_analysis(ticker: str, db: AsyncSession = Depends(get_db)):
    df = await load_bars_df(db, ticker)
    if df.empty:
        raise HTTPException(400, "No bars. Ingest data first.")
    snap = latest_snapshot(df)
    series = series_for_chart(df)
    symbol_id = await get_symbol_id(db, ticker)
    if symbol_id:
        db.add(TechnicalSnapshot(symbol_id=symbol_id, indicators=snap))
        await db.commit()
    return {"ticker": ticker, "snapshot": snap, "series": series}


@router.post("/fundamentals/ingest")
async def fundamentals_ingest(body: TickerBody, db: AsyncSession = Depends(get_db)):
    return await FundamentalService(db).ingest(body.ticker)


@router.get("/fundamentals/{ticker}")
async def fundamentals_get(ticker: str, db: AsyncSession = Depends(get_db)):
    data = await FundamentalService(db).latest(ticker)
    if not data:
        raise HTTPException(404, "No fundamentals. Call POST /fundamentals/ingest first.")
    return data


@router.post("/news/collect")
async def news_collect(body: TickerBody, db: AsyncSession = Depends(get_db)):
    return await NewsService(db).collect(body.ticker)


@router.get("/news")
async def news_list(limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(NewsArticle).order_by(NewsArticle.created_at.desc()).limit(limit))
    ).scalars().all()
    return [
        {
            "id": r.id,
            "source": r.source,
            "category": r.category,
            "title": r.title,
            "url": r.url,
            "published_at": r.published_at,
            "summary": r.summary,
            "sentiment": float(r.sentiment) if r.sentiment is not None else None,
            "sentiment_label": r.sentiment_label,
        }
        for r in rows
    ]


@router.post("/news/analyze")
async def news_analyze(body: NewsAnalyzeBody):
    llm = NewsLLMService()
    if body.mode == "summarize":
        return {"mode": body.mode, "result": await llm.summarize(body.text)}
    if body.mode == "ir":
        return {"mode": body.mode, "result": await llm.parse_ir(body.text)}
    if body.mode == "earnings":
        return {"mode": body.mode, "result": await llm.parse_earnings(body.text)}
    sent = await llm.sentiment(body.text)
    return {"mode": "sentiment", "result": sent}


@router.post("/news/{article_id}/enrich")
async def news_enrich(article_id: int, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(select(NewsArticle).where(NewsArticle.id == article_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "article not found")
    llm = NewsLLMService()
    text = f"{row.title}\n{row.raw_text or ''}"
    summary = await llm.summarize(text)
    sent = await llm.sentiment(text)
    row.summary = summary
    row.sentiment = Decimal(str(sent.get("score", 0)))
    row.sentiment_label = sent.get("label")
    await db.commit()
    # Index into RAG
    rag = RAGService(db)
    await rag.ingest_text(
        content=f"{summary}\n{text}",
        doc_type=row.category or "news",
        title=row.title,
        symbol_id=row.symbol_id,
        source_ref=row.url,
    )
    return {"id": row.id, "summary": summary, "sentiment": sent}


@router.post("/ml/predict")
async def ml_predict(body: MLPredictBody, db: AsyncSession = Depends(get_db)):
    df = await load_bars_df(db, body.ticker)
    if df.empty:
        raise HTTPException(400, "No bars. Ingest data first.")
    return {"ticker": body.ticker, **MLEnsembleService().predict(df, models=body.models)}


@router.post("/dl/predict")
async def dl_predict(body: DLPredictBody, db: AsyncSession = Depends(get_db)):
    df = await load_bars_df(db, body.ticker)
    if df.empty:
        raise HTTPException(400, "No bars. Ingest data first.")
    result = DeepLearningService().predict(
        df, model=body.model, backend=body.backend, epochs=body.epochs
    )
    return {"ticker": body.ticker, **result}


@router.post("/backtest/run")
async def backtest_run(body: BacktestBody, db: AsyncSession = Depends(get_db)):
    df = await load_bars_df(db, body.ticker, limit=500)
    if len(df) < 50:
        raise HTTPException(400, "Need at least 50 bars for backtest.")
    svc = BacktestService(db)
    return await svc.run_and_store(body.ticker, df, engine=body.engine, fast=body.fast, slow=body.slow)


@router.post("/rag/ingest")
async def rag_ingest(body: RagIngestBody, db: AsyncSession = Depends(get_db)):
    symbol_id = await get_symbol_id(db, body.ticker) if body.ticker else None
    return await RAGService(db).ingest_text(
        content=body.content,
        doc_type=body.doc_type,
        title=body.title,
        symbol_id=symbol_id,
        source_ref=body.source_ref,
    )


@router.post("/rag/query")
async def rag_query(body: RagQueryBody, db: AsyncSession = Depends(get_db)):
    result = await RAGService(db).query(body.question, limit=body.limit)
    if body.session_id:
        db.add(ChatMessage(session_id=body.session_id, role="user", content=body.question))
        db.add(
            ChatMessage(
                session_id=body.session_id,
                role="assistant",
                content=result.get("context") or "(no context)",
            )
        )
        await db.commit()
    llm = NewsLLMService()
    answer = await llm.llm.complete(
        "以下のコンテキストのみを根拠に簡潔に日本語で回答してください。",
        f"Q: {body.question}\n\nContext:\n{result.get('context')}",
    )
    result["answer"] = answer
    return result


@router.get("/brokers")
async def brokers():
    return await list_broker_status()


@router.post("/brokers/order")
async def brokers_order(body: BrokerOrderBody):
    broker = get_broker(body.broker)
    result = await broker.place_order(
        BrokerOrderRequest(
            ticker=body.ticker,
            side=body.side,
            quantity=body.quantity,
            order_type=body.order_type,
            limit_price=body.limit_price,
        )
    )
    return {
        "broker": result.broker,
        "status": result.status,
        "broker_order_id": result.broker_order_id,
        "raw": result.raw,
    }


@router.post("/risk/position-size")
async def risk_position_size(body: RiskSizeBody, db: AsyncSession = Depends(get_db)):
    qty = EnhancedRiskManager(db).position_size(
        equity=body.equity,
        price=body.price,
        stop_loss_pct=body.stop_loss_pct,
        risk_per_trade_pct=body.risk_per_trade_pct,
    )
    return {"quantity": qty, "notional": qty * body.price}


@router.post("/risk/evaluate/{ticker}")
async def risk_evaluate(ticker: str, last_price: float = Query(...), db: AsyncSession = Depends(get_db)):
    symbol_id = await get_symbol_id(db, ticker)
    if not symbol_id:
        raise HTTPException(404, "symbol not found")
    triggered = await EnhancedRiskManager(db).evaluate_marks(symbol_id, last_price)
    return {"ticker": ticker, "triggered": triggered}
