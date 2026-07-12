import asyncio

from app.agents.pipeline import TradingAgentPipeline
from app.db.session import AsyncSessionLocal
from app.services.ingestion import DataIngestionService
from app.workers.celery_app import celery_app


def _run(coro):
    return asyncio.run(coro)


@celery_app.task(name="app.workers.tasks.ingest_macro_task")
def ingest_macro_task():
    async def _inner():
        async with AsyncSessionLocal() as db:
            svc = DataIngestionService(db)
            return await svc.ingest_macro()

    return _run(_inner())


@celery_app.task(name="app.workers.tasks.ingest_bars_task")
def ingest_bars_task(ticker: str, timeframe: str = "1d"):
    async def _inner():
        async with AsyncSessionLocal() as db:
            svc = DataIngestionService(db)
            return await svc.ingest_bars(ticker, timeframe=timeframe)

    return _run(_inner())


@celery_app.task(name="app.workers.tasks.run_pipeline_task")
def run_pipeline_task(ticker: str, quantity: float = 100):
    async def _inner():
        async with AsyncSessionLocal() as db:
            pipeline = TradingAgentPipeline(db)
            return await pipeline.run(ticker, quantity=quantity)

    return _run(_inner())


@celery_app.task(name="app.workers.tasks.run_watchlist_pipeline")
def run_watchlist_pipeline(tickers: list[str]):
    results = []
    for t in tickers:
        results.append(run_pipeline_task(t))
    return results
