from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pipeline import TradingAgentPipeline
from app.config import get_settings
from app.db.session import get_db
from app.models import (
    MacroSeries,
    MarketBar,
    Order,
    PipelineRun,
    PortfolioSnapshot,
    Position,
    Prediction,
    RiskEvent,
    SnsPost,
    Symbol,
    TradingSignal,
)
from app.schemas import (
    BarOut,
    HealthResponse,
    IngestRequest,
    MacroOut,
    OrderOut,
    PipelineRequest,
    PipelineResponse,
    PortfolioOut,
    PositionOut,
    PredictRequest,
    PredictionOut,
    RiskEventOut,
    SignalOut,
    SnsPostOut,
    SymbolOut,
)
from app.services.ingestion import DataIngestionService
from app.services.prediction import PredictionService

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    providers: list[dict] = [{"name": "yahoo", "available": True}]
    try:
        ingestion = DataIngestionService(db)
        providers = await ingestion.provider_status()
    except Exception:  # noqa: BLE001
        pass
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        trading_mode=settings.trading_mode,
        providers=providers,
    )


@router.get("/health/live")
async def health_live():
    """DB-free liveness for Railway healthchecks."""
    return {"status": "ok"}


@router.get("/symbols", response_model=list[SymbolOut])
async def list_symbols(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Symbol).where(Symbol.is_active.is_(True)).order_by(Symbol.ticker))).scalars().all()
    return rows


@router.post("/ingest/bars")
async def ingest_bars(body: IngestRequest, db: AsyncSession = Depends(get_db)):
    try:
        svc = DataIngestionService(db)
        result = await svc.ingest_bars(body.ticker, timeframe=body.timeframe, limit=body.limit)
        if result.get("bars", 0) == 0:
            return {**result, "warning": "0 bars ingested — Yahoo may be blocked or ticker invalid"}
        return result
    except Exception as e:
        raise HTTPException(500, f"Ingest failed: {e}") from e


@router.post("/ingest/macro")
async def ingest_macro(db: AsyncSession = Depends(get_db)):
    svc = DataIngestionService(db)
    return await svc.ingest_macro()


@router.get("/market/{ticker}/bars", response_model=list[BarOut])
async def get_bars(
    ticker: str,
    timeframe: str = "1d",
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    sym = (await db.execute(select(Symbol).where(Symbol.ticker == ticker))).scalar_one_or_none()
    if not sym:
        raise HTTPException(404, f"Symbol {ticker} not found")
    rows = (
        await db.execute(
            select(MarketBar)
            .where(MarketBar.symbol_id == sym.id, MarketBar.timeframe == timeframe)
            .order_by(MarketBar.ts.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        BarOut(
            ts=r.ts,
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=float(r.volume or 0),
            source=r.source,
        )
        for r in reversed(rows)
    ]


@router.get("/macro", response_model=list[MacroOut])
async def get_macro(db: AsyncSession = Depends(get_db)):
    # latest per series_code
    rows = (await db.execute(select(MacroSeries).order_by(MacroSeries.ts.desc()).limit(200))).scalars().all()
    seen: set[str] = set()
    latest: list[MacroOut] = []
    for r in rows:
        if r.series_code in seen:
            continue
        seen.add(r.series_code)
        latest.append(MacroOut(series_code=r.series_code, ts=r.ts, value=float(r.value), source=r.source))
    return latest


@router.post("/predict")
async def predict(body: PredictRequest, db: AsyncSession = Depends(get_db)):
    svc = PredictionService(db)
    result = await svc.predict(body.ticker, horizon=body.horizon)
    if not result:
        raise HTTPException(400, "Insufficient data for prediction. Ingest bars first.")
    return result


@router.get("/predictions", response_model=list[PredictionOut])
async def list_predictions(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(Prediction).order_by(Prediction.predicted_at.desc()).limit(limit))
    ).scalars().all()
    return [
        PredictionOut(
            id=r.id,
            model_name=r.model_name,
            horizon=r.horizon,
            predicted_at=r.predicted_at,
            predicted_price=float(r.predicted_price) if r.predicted_price is not None else None,
            direction=r.direction,
            confidence=float(r.confidence) if r.confidence is not None else None,
        )
        for r in rows
    ]


@router.post("/pipeline/run", response_model=PipelineResponse)
async def run_pipeline(body: PipelineRequest, db: AsyncSession = Depends(get_db)):
    pipeline = TradingAgentPipeline(db)
    result = await pipeline.run(body.ticker, quantity=body.quantity)
    return PipelineResponse(**result)


@router.get("/signals", response_model=list[SignalOut])
async def list_signals(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(TradingSignal).order_by(TradingSignal.created_at.desc()).limit(limit))
    ).scalars().all()
    return [
        SignalOut(
            id=r.id,
            signal_type=r.signal_type,
            strength=float(r.strength) if r.strength is not None else None,
            rationale=r.rationale,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Order).order_by(Order.created_at.desc()).limit(limit))).scalars().all()
    return [
        OrderOut(
            id=r.id,
            side=r.side,
            quantity=float(r.quantity),
            status=r.status,
            mode=r.mode,
            avg_fill_price=float(r.avg_fill_price) if r.avg_fill_price is not None else None,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/positions", response_model=list[PositionOut])
async def list_positions(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Position))).scalars().all()
    out = []
    for r in rows:
        sym = (await db.execute(select(Symbol).where(Symbol.id == r.symbol_id))).scalar_one_or_none()
        out.append(
            PositionOut(
                id=r.id,
                symbol_id=r.symbol_id,
                ticker=sym.ticker if sym else None,
                quantity=float(r.quantity),
                avg_cost=float(r.avg_cost) if r.avg_cost is not None else None,
                unrealized_pnl=float(r.unrealized_pnl),
                realized_pnl=float(r.realized_pnl),
            )
        )
    return out


@router.get("/risk/events", response_model=list[RiskEventOut])
async def list_risk_events(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(RiskEvent).order_by(RiskEvent.created_at.desc()).limit(limit))
    ).scalars().all()
    return rows


@router.get("/portfolio/snapshots", response_model=list[PortfolioOut])
async def portfolio_snapshots(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(PortfolioSnapshot).order_by(PortfolioSnapshot.ts.desc()).limit(limit))
    ).scalars().all()
    return [
        PortfolioOut(
            id=r.id,
            ts=r.ts,
            equity=float(r.equity),
            cash=float(r.cash),
            exposure=float(r.exposure),
            daily_pnl=float(r.daily_pnl),
        )
        for r in rows
    ]


@router.get("/sns/posts", response_model=list[SnsPostOut])
async def list_sns_posts(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SnsPost).order_by(SnsPost.created_at.desc()).limit(limit))).scalars().all()
    return rows


@router.get("/pipeline/runs")
async def pipeline_runs(limit: int = 100, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit))
    ).scalars().all()
    return [
        {
            "id": r.id,
            "stage": r.stage,
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "details": r.details,
        }
        for r in rows
    ]
