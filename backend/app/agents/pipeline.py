"""End-to-end agent pipeline: collect → analyze → predict → decide → order → risk → monitor → SNS."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.technical import latest_snapshot
from app.models import MarketBar, PipelineRun, PortfolioSnapshot, Symbol
from app.services.ingestion import DataIngestionService
from app.services.market_data import load_bars_df
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

    async def run(
        self,
        ticker: str,
        quantity: float = 100,
        dry_run: bool = False,
        auto_size: bool = True,
    ) -> dict:
        result: dict = {"ticker": ticker, "dry_run": dry_run, "stages": {}}

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
        df = await load_bars_df(self.db, ticker, limit=250)
        tech = latest_snapshot(df) if not df.empty else {}
        analysis = {
            "last_close": float(bar.close) if bar else None,
            "last_volume": float(bar.volume) if bar else None,
            "last_ts": bar.ts.isoformat() if bar else None,
            "trend": tech.get("trend"),
            "rsi_14": tech.get("rsi_14"),
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
                "evidence_ok": pred.evidence_ok,
                "oos_hit_rate": pred.oos_hit_rate,
            },
        )
        result["stages"]["predict"] = {
            "direction": pred.direction,
            "confidence": pred.confidence,
            "predicted_price": pred.predicted_price,
            "model": pred.model_name,
            "evidence_ok": pred.evidence_ok,
            "oos_hit_rate": pred.oos_hit_rate,
            "evidence": pred.evidence,
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
        from app.trading.edge import assess_edge

        price = analysis["last_close"] or pred.predicted_price
        equity, daily_pnl = await self.orders.book_equity()
        plan = assess_edge(
            evidence=pred.evidence,
            direction=pred.direction,
            last_close=float(price or 0),
            predicted_price=float(pred.predicted_price),
            trend=analysis.get("trend"),
            rsi=analysis.get("rsi_14"),
            equity=equity,
            risk=self.orders.risk,
        )
        result["stages"]["edge"] = plan
        sized_qty = float(plan.get("suggested_qty") or 0) if auto_size else float(quantity)
        if auto_size and sized_qty <= 0:
            sized_qty = 0.0
        if not auto_size:
            sized_qty = float(quantity)

        signal = await self.decision.decide(
            symbol_id=sym.id,
            direction=pred.direction,
            confidence=pred.confidence,
            prediction_id=latest_pred.id,
            evidence_ok=pred.evidence_ok,
            oos_hit_rate=pred.oos_hit_rate,
            evidence_reason=(pred.evidence or {}).get("block_reason") if pred.evidence else None,
            profit_action=plan.get("action"),
            profit_reason=plan.get("block_reason"),
        )
        await self._log_stage(
            "decide",
            "success",
            {
                "signal": signal.signal_type,
                "rationale": signal.rationale,
                "suggested_qty": sized_qty,
                "edge_ok": plan.get("ok"),
            },
        )
        result["stages"]["decide"] = {
            "signal": signal.signal_type,
            "id": signal.id,
            "suggested_qty": sized_qty,
            "edge": plan,
        }

        # 5–6. Order + risk (risk embedded in OrderService)
        quantity = sized_qty
        if dry_run:
            ev = await self.orders.evaluate_manual(
                ticker=ticker,
                side=signal.signal_type if signal.signal_type in {"buy", "sell"} else "buy",
                quantity=quantity,
                price=float(price),
            )
            if signal.signal_type == "hold":
                ev = {**ev, "decision": "blocked", "ok": False, "risk_reason": signal.rationale}
            await self._log_stage("order", "skipped", {"dry_run": True, **ev})
            await self._log_stage("risk", "success", {"checked": True, "dry_run": True})
            result["stages"]["order"] = {"dry_run": True, **ev}
            result["stages"]["risk"] = {"checked": True, "dry_run": True}
            order = None
        else:
            order = await self.orders.place_from_signal(
                signal, quantity=quantity, price=price, equity=equity, daily_pnl=daily_pnl
            )
            await self._log_stage(
                "order",
                "success" if order else "skipped",
                {"order_id": order.id if order else None, "status": order.status if order else "none"},
            )
            await self._log_stage("risk", "success", {"checked": True})
            result["stages"]["order"] = {"order_id": order.id if order else None}
            result["stages"]["risk"] = {"checked": True}

        # 7. Monitor — portfolio snapshot from book
        fill_notional = quantity * float(price)
        snap = PortfolioSnapshot(
            equity=Decimal(str(round(equity, 2))),
            cash=Decimal(str(round(max(equity - fill_notional, 0), 2))),
            exposure=Decimal(str(round(fill_notional if order else 0, 2))),
            daily_pnl=Decimal(str(round(daily_pnl, 2))),
            meta={"ticker": ticker, "signal": signal.signal_type, "dry_run": dry_run},
        )
        self.db.add(snap)
        await self.db.commit()
        await self._log_stage("monitor", "success", {"equity": equity})
        result["stages"]["monitor"] = {"equity": equity}

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
