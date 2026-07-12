"""End-to-end agent pipeline: collect → analyze → predict → decide → order → risk → monitor → SNS."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MarketBar, PipelineRun, PortfolioSnapshot, Symbol
from app.services.ingestion import DataIngestionService
from app.services.prediction import PredictionService
from app.services.sns import SnsService
from app.services.trading import DecisionEngine, OrderService


class TradingAgentPipeline:
    STAGES = (
        "collect",
        "analyze",
        "predict",
        "decide",
        "order",
        "risk",
        "monitor",
        "sns",
    )

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.ingestion = DataIngestionService(db)
        self.prediction = PredictionService(db)
        self.decision = DecisionEngine(db)
        self.orders = OrderService(db)
        self.sns = SnsService(db)

    async def _log_stage(self, stage: str, status: str, details: dict | None = None) -> PipelineRun:
        run = PipelineRun(stage=stage, status=status, details=details or {})
        if status in ("success", "failed", "skipped"):
            run.finished_at = datetime.now(timezone.utc)
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def run(self, ticker: str, quantity: float = 100) -> dict:
        result: dict = {"ticker": ticker, "stages": {}}

        # 1. Collect
        try:
            ingest = await self.ingestion.ingest_bars(ticker)
            await self.ingestion.ingest_macro()
            await self._log_stage("collect", "success", ingest)
            result["stages"]["collect"] = ingest
        except Exception as e:
            await self._log_stage("collect", "failed", {"error": str(e)})
            result["error"] = str(e)
            return result

        # 2. Analyze (latest bar snapshot)
        sym = (await self.db.execute(select(Symbol).where(Symbol.ticker == ticker))).scalar_one_or_none()
        if not sym:
            result["error"] = "symbol missing after ingest"
            return result
        bar = (
            await self.db.execute(
                select(MarketBar)
                .where(MarketBar.symbol_id == sym.id, MarketBar.timeframe == "1d")
                .order_by(MarketBar.ts.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        analysis = {
            "last_close": float(bar.close) if bar else None,
            "last_volume": float(bar.volume) if bar else None,
            "last_ts": bar.ts.isoformat() if bar else None,
        }
        await self._log_stage("analyze", "success", analysis)
        result["stages"]["analyze"] = analysis

        # 3. Predict
        pred = await self.prediction.predict(ticker)
        if not pred:
            await self._log_stage("predict", "failed", {"reason": "insufficient data"})
            result["stages"]["predict"] = {"status": "failed"}
            return result
        await self._log_stage(
            "predict",
            "success",
            {
                "direction": pred.direction,
                "confidence": pred.confidence,
                "predicted_price": pred.predicted_price,
            },
        )
        result["stages"]["predict"] = {
            "direction": pred.direction,
            "confidence": pred.confidence,
            "predicted_price": pred.predicted_price,
            "model": pred.model_name,
        }

        # 4. Decide
        # Get latest prediction id
        from app.models import Prediction

        latest_pred = (
            await self.db.execute(
                select(Prediction)
                .where(Prediction.symbol_id == sym.id)
                .order_by(Prediction.predicted_at.desc())
                .limit(1)
            )
        ).scalar_one()
        signal = await self.decision.decide(
            symbol_id=sym.id,
            direction=pred.direction,
            confidence=pred.confidence,
            prediction_id=latest_pred.id,
        )
        await self._log_stage(
            "decide",
            "success",
            {"signal": signal.signal_type, "rationale": signal.rationale},
        )
        result["stages"]["decide"] = {"signal": signal.signal_type, "id": signal.id}

        # 5–6. Order + risk (risk embedded in OrderService)
        price = analysis["last_close"] or pred.predicted_price
        order = await self.orders.place_from_signal(signal, quantity=quantity, price=price)
        await self._log_stage(
            "order",
            "success" if order else "skipped",
            {"order_id": order.id if order else None, "status": order.status if order else "none"},
        )
        await self._log_stage("risk", "success", {"checked": True})
        result["stages"]["order"] = {"order_id": order.id if order else None}
        result["stages"]["risk"] = {"checked": True}

        # 7. Monitor — portfolio snapshot (simplified)
        snap = PortfolioSnapshot(
            equity=Decimal("10000000"),
            cash=Decimal("8000000"),
            exposure=Decimal(str(quantity * price)),
            daily_pnl=Decimal("0"),
            meta={"ticker": ticker, "signal": signal.signal_type},
        )
        self.db.add(snap)
        await self.db.commit()
        await self._log_stage("monitor", "success", {"equity": 10_000_000})
        result["stages"]["monitor"] = {"equity": 10_000_000}

        # 8. SNS draft
        post = await self.sns.create_draft(
            ticker=ticker,
            direction=pred.direction,
            confidence=pred.confidence,
            predicted_price=pred.predicted_price,
        )
        await self._log_stage("sns", "success", {"post_id": post.id, "status": post.status})
        result["stages"]["sns"] = {"post_id": post.id, "status": post.status}

        result["status"] = "completed"
        return result
