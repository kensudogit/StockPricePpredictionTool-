"""Daily ops: watchlist scan, mark-to-market, stop/take flatten."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.evidence import build_ols_evidence
from app.analysis.technical import latest_snapshot
from app.config import get_settings
from app.models import Order, PortfolioSnapshot, Position, Symbol
from app.risk.manager import EnhancedRiskManager
from app.services.ingestion import DataIngestionService
from app.services.market_data import load_bars_df
from app.services.prediction import PredictionService
from app.services.trading import OrderService
from app.trading.edge import assess_edge
from app.trading.expectancy import allocate_book


def flatten_side(quantity: float) -> str:
    return "sell" if quantity > 0 else "buy"


def parse_watchlist(raw: str | None = None) -> list[str]:
    if raw is None:
        return get_settings().watchlist_tickers
    return [t.strip() for t in raw.split(",") if t.strip()]


class OpsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.ingestion = DataIngestionService(db)
        self.orders = OrderService(db)
        self.risk = EnhancedRiskManager(db)

    async def open_tickers(self) -> set[str]:
        rows = (
            await self.db.execute(
                select(Symbol.ticker)
                .join(Position, Position.symbol_id == Symbol.id)
                .where(Position.quantity != 0)
            )
        ).all()
        return {r[0] for r in rows}

    async def scan_ticker(self, ticker: str) -> dict[str, Any]:
        try:
            await self.ingestion.ingest_bars(ticker, timeframe="1d", limit=220)
        except Exception as e:  # noqa: BLE001
            return {"ticker": ticker, "ok": False, "error": str(e)}
        df = await load_bars_df(self.db, ticker, limit=250)
        if df.empty or len(df) < 40:
            return {"ticker": ticker, "ok": False, "error": "insufficient bars"}
        pred = await PredictionService(self.db).predict(ticker)
        if not pred:
            return {"ticker": ticker, "ok": False, "error": "prediction failed"}
        tech = latest_snapshot(df)
        equity, _ = await self.orders.book_equity()
        evidence = pred.evidence or build_ols_evidence(
            df,
            min_hit_rate=self.settings.min_oos_hit_rate,
            min_samples=self.settings.min_oos_samples,
            fee_bps=self.settings.paper_fee_bps,
        )
        plan = assess_edge(
            evidence=evidence,
            direction=pred.direction,
            last_close=float(tech.get("close") or df.iloc[-1]["close"]),
            predicted_price=float(pred.predicted_price),
            trend=tech.get("trend"),
            rsi=tech.get("rsi_14"),
            equity=equity,
            risk=self.risk,
        )
        return {
            "ticker": ticker,
            "ok": bool(plan.get("ok")),
            "action": plan.get("action"),
            "last_close": tech.get("close"),
            "predicted_price": pred.predicted_price,
            "plan": plan,
        }

    async def scan_watchlist(self, tickers: list[str] | None = None) -> dict[str, Any]:
        names = tickers or self.settings.watchlist_tickers
        rows = []
        for t in names[:12]:
            rows.append(await self.scan_ticker(t))
        actionable = [r for r in rows if r.get("ok") and r.get("action") in {"buy", "sell"}]
        equity, _ = await self.orders.book_equity()
        allocation = allocate_book(
            actionable,
            equity=equity,
            risk_per_trade_pct=self.settings.risk_per_trade_pct,
            max_new_trades=self.settings.max_new_trades_per_day,
            max_position_pct=self.settings.max_position_pct,
            stop_loss_pct=self.settings.default_stop_loss_pct,
            open_tickers=await self.open_tickers(),
        )
        return {
            "tickers": names,
            "scanned": len(rows),
            "actionable": actionable,
            "allocation": allocation,
            "skipped": [r for r in rows if not r.get("ok") or r.get("action") == "hold"],
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    async def mark_and_exit(self, *, execute: bool = True) -> dict[str, Any]:
        rows = (await self.db.execute(select(Position).where(Position.quantity != 0))).scalars().all()
        marks: list[dict[str, Any]] = []
        exits: list[dict[str, Any]] = []
        equity, daily_pnl = await self.orders.book_equity()
        nav = 0.0
        for pos in rows:
            sym = (
                await self.db.execute(select(Symbol).where(Symbol.id == pos.symbol_id))
            ).scalar_one_or_none()
            if not sym:
                continue
            try:
                await self.ingestion.ingest_bars(sym.ticker, timeframe="1d", limit=40)
            except Exception:  # noqa: BLE001
                pass
            df = await load_bars_df(self.db, sym.ticker, limit=5)
            if df.empty:
                marks.append({"ticker": sym.ticker, "error": "no price"})
                continue
            last = float(df.iloc[-1]["close"])
            qty = float(pos.quantity)
            avg = float(pos.avg_cost or 0)
            unreal = (last - avg) * qty if qty >= 0 else (avg - last) * abs(qty)
            pos.unrealized_pnl = Decimal(str(round(unreal, 4)))
            nav += qty * last
            trail = await self.risk.trail_stop(pos, last)
            triggered = await self.risk.evaluate_marks(pos.symbol_id, last)
            item = {
                "ticker": sym.ticker,
                "quantity": qty,
                "last": last,
                "unrealized_pnl": unreal,
                "trail": trail,
                "triggered": triggered,
            }
            marks.append(item)
            if triggered and execute:
                side = flatten_side(qty)
                out = await self.orders.place_manual(
                    symbol_id=pos.symbol_id,
                    ticker=sym.ticker,
                    side=side,
                    quantity=abs(qty),
                    price=last,
                    skip_cooldown=True,
                    flatten=True,
                    equity=equity,
                    daily_pnl=daily_pnl,
                )
                item["exit"] = out
                exits.append({"ticker": sym.ticker, "side": side, "ok": out.get("ok"), "error": out.get("error")})
        snap = PortfolioSnapshot(
            equity=Decimal(str(round(equity + nav, 2))),
            cash=Decimal(str(round(max(equity - nav, 0), 2))),
            exposure=Decimal(str(round(abs(nav), 2))),
            daily_pnl=Decimal(str(round(daily_pnl + sum(float(m.get("unrealized_pnl") or 0) for m in marks if "unrealized_pnl" in m), 2))),
            meta={"marks": len(marks), "exits": len(exits)},
        )
        self.db.add(snap)
        await self.db.commit()
        return {"marks": marks, "exits": exits, "positions": len(rows)}

    async def daily_run(self, *, execute: bool | None = None) -> dict[str, Any]:
        do_exec = self.settings.daily_auto_execute if execute is None else execute
        scan = await self.scan_watchlist()
        book = await self.mark_and_exit(execute=True)
        placed = []
        picks = (scan.get("allocation") or {}).get("picks") or []
        if do_exec:
            pipeline = __import__("app.agents.pipeline", fromlist=["TradingAgentPipeline"]).TradingAgentPipeline
            pipe = pipeline(self.db)
            for pick in picks:
                qty = float(pick.get("quantity") or 0)
                if qty <= 0:
                    continue
                placed.append(
                    await pipe.run(pick["ticker"], quantity=qty, dry_run=False, auto_size=False)
                )
        expect = await self.expectancy_report()
        return {
            "execute": do_exec,
            "scan": scan,
            "book": book,
            "placed": placed,
            "expectancy": expect,
            "note": "execute=false は配分評価と値洗いのみ。自動発注は DAILY_AUTO_EXECUTE=true。利益は保証しない。",
        }

    async def expectancy_report(self) -> dict[str, Any]:
        start = float(self.settings.starting_equity)
        equity, daily_pnl = await self.orders.book_equity()
        realized = float(
            (
                await self.db.execute(select(func.coalesce(func.sum(Position.realized_pnl), 0)))
            ).scalar_one()
            or 0
        )
        unreal = float(
            (
                await self.db.execute(
                    select(func.coalesce(func.sum(Position.unrealized_pnl), 0)).where(Position.quantity != 0)
                )
            ).scalar_one()
            or 0
        )
        n_fills = int(
            (
                await self.db.execute(select(func.count()).select_from(Order).where(Order.status == "filled"))
            ).scalar_one()
            or 0
        )
        snaps = (
            await self.db.execute(
                select(PortfolioSnapshot).order_by(PortfolioSnapshot.ts.desc()).limit(20)
            )
        ).scalars().all()
        curve = [{"ts": s.ts.isoformat() if s.ts else None, "equity": float(s.equity)} for s in reversed(snaps)]
        per_fill = (realized / n_fills) if n_fills else 0.0
        return {
            "starting_equity": start,
            "equity": equity,
            "daily_pnl": daily_pnl,
            "equity_delta": round(equity - start, 2),
            "equity_return": round((equity - start) / start, 6) if start else 0.0,
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unreal, 2),
            "n_filled_orders": n_fills,
            "expectancy_per_fill": round(per_fill, 2),
            "curve": curve,
            "note": "実現損益÷約定回数。OOS EV が机上、ここが実測。利益は保証しない。",
        }
