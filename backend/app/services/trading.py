"""Trading decision + paper order execution + risk checks."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import desc

from app.config import get_settings
from app.models import Order, PortfolioSnapshot, Position, RiskEvent, TradingSignal
from app.risk.manager import EnhancedRiskManager
from app.trading.gate import can_place


class RiskManager(EnhancedRiskManager):
    """Backward-compatible alias used by OrderService."""

    async def check_order(
        self,
        *,
        equity: float,
        order_notional: float,
        daily_pnl: float,
        opening_new: bool = True,
    ) -> tuple[bool, str]:
        return await super().check_order(
            equity=equity,
            order_notional=order_notional,
            daily_pnl=daily_pnl,
            opening_new=opening_new,
        )


class DecisionEngine:
    """Convert predictions into buy/sell/hold signals."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def decide(
        self,
        symbol_id: int,
        direction: str,
        confidence: float,
        prediction_id: int | None = None,
        min_confidence: float = 0.55,
        evidence_ok: bool = True,
        oos_hit_rate: float | None = None,
        evidence_reason: str | None = None,
        profit_action: str | None = None,
        profit_reason: str | None = None,
    ) -> TradingSignal:
        if profit_action == "hold":
            signal_type = "hold"
            rationale = profit_reason or "profit gate blocked"
        elif not evidence_ok:
            signal_type = "hold"
            rationale = evidence_reason or "OOS evidence missing or below threshold"
        elif oos_hit_rate is not None and oos_hit_rate < min_confidence:
            signal_type = "hold"
            rationale = f"OOS hit rate {oos_hit_rate:.2f} below threshold {min_confidence}"
        elif confidence < min_confidence:
            signal_type = "hold"
            rationale = f"Confidence {confidence:.2f} below threshold {min_confidence}"
        elif profit_action in {"buy", "sell"}:
            signal_type = profit_action
            rationale = (
                f"profit gate {profit_action}"
                + (f" oos_hit={oos_hit_rate:.2f}" if oos_hit_rate is not None else "")
            )
        elif direction == "up":
            signal_type = "buy"
            rationale = (
                f"Model expects upside in-sample={confidence:.2f}"
                + (f" oos_hit={oos_hit_rate:.2f}" if oos_hit_rate is not None else "")
            )
        else:
            signal_type = "sell"
            rationale = (
                f"Model expects downside in-sample={confidence:.2f}"
                + (f" oos_hit={oos_hit_rate:.2f}" if oos_hit_rate is not None else "")
            )

        signal = TradingSignal(
            symbol_id=symbol_id,
            signal_type=signal_type,
            strength=Decimal(str(round(confidence, 4))),
            rationale=rationale,
            prediction_id=prediction_id,
            status="pending",
        )
        self.db.add(signal)
        await self.db.commit()
        await self.db.refresh(signal)
        return signal


class OrderService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.risk = RiskManager(db)

    def _paper_fill_price(self, side: str, price: float) -> float:
        fee = float(self.settings.paper_fee_bps) / 10000.0
        if side == "buy":
            return max(0.01, price * (1.0 + fee))
        return max(0.01, price * (1.0 - fee))

    async def _cooldown_blocked(self) -> tuple[bool, str]:
        cd = int(self.settings.trade_cooldown_seconds or 0)
        if cd <= 0:
            return False, "ok"
        last = (
            await self.db.execute(select(Order).order_by(desc(Order.created_at)).limit(1))
        ).scalar_one_or_none()
        if not last or not last.created_at:
            return False, "ok"
        ts = last.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - ts).total_seconds()
        if elapsed < cd:
            return True, f"cooldown {cd - int(elapsed)}s remaining"
        return False, "ok"

    async def book_equity(self) -> tuple[float, float]:
        snap = (
            await self.db.execute(
                select(PortfolioSnapshot).order_by(desc(PortfolioSnapshot.ts)).limit(1)
            )
        ).scalar_one_or_none()
        if snap:
            return float(snap.equity), float(snap.daily_pnl)
        return float(self.settings.starting_equity), 0.0

    async def place_from_signal(
        self,
        signal: TradingSignal,
        quantity: float,
        price: float,
        equity: float = 10_000_000,
        daily_pnl: float = 0,
    ) -> Order | None:
        if signal.signal_type == "hold":
            signal.status = "skipped"
            await self.db.commit()
            return None

        allowed, gate_reason = can_place(
            mode=self.settings.trading_mode,
            broker=self.settings.broker_name,
            settings=self.settings,
        )
        if not allowed:
            signal.status = "rejected"
            self.db.add(
                RiskEvent(
                    event_type="order_blocked",
                    severity="warning",
                    message=gate_reason,
                    details={"signal_id": signal.id},
                )
            )
            await self.db.commit()
            return None

        cooling, cool_reason = await self._cooldown_blocked()
        if cooling:
            signal.status = "rejected"
            self.db.add(
                RiskEvent(
                    event_type="order_blocked",
                    severity="info",
                    message=cool_reason,
                    details={"signal_id": signal.id},
                )
            )
            await self.db.commit()
            return None

        if equity == 10_000_000:
            equity, daily_pnl = await self.book_equity()

        fill_px = (
            self._paper_fill_price(signal.signal_type, price)
            if self.settings.trading_mode == "paper"
            else price
        )
        notional = quantity * fill_px
        ok, reason = await self.risk.check_order(equity=equity, order_notional=notional, daily_pnl=daily_pnl)
        if not ok:
            signal.status = "rejected"
            await self.db.commit()
            self.db.add(
                RiskEvent(
                    event_type="order_rejected",
                    severity="warning",
                    message=reason,
                    details={"signal_id": signal.id},
                )
            )
            await self.db.commit()
            return None

        mode = self.settings.trading_mode
        order = Order(
            symbol_id=signal.symbol_id,
            signal_id=signal.id,
            side=signal.signal_type,
            order_type="market",
            quantity=Decimal(str(quantity)),
            status="filled" if mode == "paper" else "submitted",
            mode=mode,
            filled_qty=Decimal(str(quantity)) if mode == "paper" else Decimal("0"),
            avg_fill_price=Decimal(str(fill_px)) if mode == "paper" else None,
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(order)
        signal.status = "executed"
        if mode == "paper":
            await self._update_position(signal.symbol_id, signal.signal_type, quantity, fill_px)
            await self.db.flush()
            pos = (
                await self.db.execute(select(Position).where(Position.symbol_id == signal.symbol_id))
            ).scalar_one_or_none()
            if pos and signal.signal_type == "buy":
                await self.risk.attach_stops(
                    position_id=pos.id,
                    symbol_id=signal.symbol_id,
                    side="buy",
                    entry_price=fill_px,
                    quantity=quantity,
                )
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def place_manual(
        self,
        *,
        symbol_id: int,
        ticker: str,
        side: str,
        quantity: float,
        price: float,
        broker_name: str | None = None,
        order_type: str = "market",
        limit_price: float | None = None,
        equity: float = 10_000_000,
        daily_pnl: float = 0,
        skip_cooldown: bool = False,
        flatten: bool = False,
    ) -> dict:
        """Manual buy/sell: gate → risk check → broker → persist order/position."""
        from app.brokers import get_broker
        from app.brokers.base import BrokerOrderRequest

        side = side.lower().strip()
        if side not in {"buy", "sell"}:
            return {"ok": False, "error": "side must be buy or sell"}
        if quantity <= 0:
            return {"ok": False, "error": "quantity must be positive"}
        if price <= 0:
            return {"ok": False, "error": "price must be positive"}

        broker = (broker_name or self.settings.broker_name or "paper").lower()
        allowed, gate_reason = can_place(
            mode=self.settings.trading_mode, broker=broker, settings=self.settings
        )
        if not allowed:
            self.db.add(
                RiskEvent(
                    event_type="order_blocked",
                    severity="warning",
                    message=gate_reason,
                    details={"ticker": ticker, "side": side, "broker": broker},
                )
            )
            await self.db.commit()
            return {"ok": False, "error": gate_reason, "blocked": True}

        cooling, cool_reason = (False, "ok") if skip_cooldown or flatten else await self._cooldown_blocked()
        if cooling:
            return {"ok": False, "error": cool_reason, "blocked": True}

        if equity == 10_000_000:
            equity, daily_pnl = await self.book_equity()

        raw_price = float(limit_price) if order_type == "limit" and limit_price else float(price)
        fill_price = (
            self._paper_fill_price(side, raw_price)
            if self.settings.trading_mode == "paper" and broker == "paper"
            else raw_price
        )
        notional = quantity * fill_price
        ok, reason = await self.risk.check_order(
            equity=equity,
            order_notional=notional,
            daily_pnl=daily_pnl,
            opening_new=not flatten,
        )
        if not ok:
            self.db.add(
                RiskEvent(
                    event_type="order_rejected",
                    severity="warning",
                    message=reason,
                    details={"ticker": ticker, "side": side, "quantity": quantity, "flatten": flatten},
                )
            )
            await self.db.commit()
            return {"ok": False, "error": reason, "rejected": True}

        broker = get_broker(broker)
        broker_result = await broker.place_order(
            BrokerOrderRequest(
                ticker=ticker,
                side=side,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
            )
        )
        if broker_result.status in {"unconfigured", "stub", "error"}:
            return {
                "ok": False,
                "error": f"broker {broker_result.broker}: {broker_result.status}",
                "broker": broker_result.broker,
                "raw": broker_result.raw,
            }

        mode = self.settings.trading_mode
        if mode == "paper" and broker_result.broker == "paper":
            status = "filled"
        elif broker_result.status == "filled":
            status = "filled"
        else:
            status = broker_result.status

        order = Order(
            symbol_id=symbol_id,
            signal_id=None,
            side=side,
            order_type=order_type,
            quantity=Decimal(str(quantity)),
            limit_price=Decimal(str(limit_price)) if limit_price is not None else None,
            status=status,
            mode=mode,
            broker_order_id=broker_result.broker_order_id,
            filled_qty=Decimal(str(quantity)) if status == "filled" else Decimal("0"),
            avg_fill_price=Decimal(str(fill_price)) if status == "filled" else None,
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(order)

        if status == "filled":
            await self._update_position(symbol_id, side, quantity, fill_price)
            await self.db.flush()
            pos = (
                await self.db.execute(select(Position).where(Position.symbol_id == symbol_id))
            ).scalar_one_or_none()
            if pos and not flatten and float(pos.quantity) != 0:
                await self.risk.attach_stops(
                    position_id=pos.id,
                    symbol_id=symbol_id,
                    side="buy" if float(pos.quantity) > 0 else "sell",
                    entry_price=fill_price,
                    quantity=abs(float(pos.quantity)),
                )

        await self.db.commit()
        await self.db.refresh(order)
        return {
            "ok": True,
            "order_id": order.id,
            "broker": broker_result.broker,
            "status": order.status,
            "broker_order_id": order.broker_order_id,
            "side": side,
            "quantity": quantity,
            "avg_fill_price": float(order.avg_fill_price) if order.avg_fill_price is not None else None,
            "mode": order.mode,
            "ticker": ticker,
            "fee_bps": self.settings.paper_fee_bps if order.mode == "paper" else 0,
            "equity_used": equity,
            "raw": broker_result.raw,
        }

    async def evaluate_manual(
        self,
        *,
        ticker: str,
        side: str,
        quantity: float,
        price: float,
        broker_name: str | None = None,
        order_type: str = "market",
        limit_price: float | None = None,
    ) -> dict:
        side = side.lower().strip()
        broker = (broker_name or self.settings.broker_name or "paper").lower()
        allowed, gate_reason = can_place(
            mode=self.settings.trading_mode, broker=broker, settings=self.settings
        )
        equity, daily_pnl = await self.book_equity()
        raw_price = float(limit_price) if order_type == "limit" and limit_price else float(price)
        fill_price = (
            self._paper_fill_price(side, raw_price)
            if self.settings.trading_mode == "paper" and broker == "paper"
            else raw_price
        )
        notional = quantity * fill_price
        cooling, cool_reason = await self._cooldown_blocked()
        risk_ok, risk_reason = await self.risk.check_order(
            equity=equity, order_notional=notional, daily_pnl=daily_pnl
        )
        decision = (
            "ready"
            if allowed and risk_ok and not cooling and side in {"buy", "sell"} and quantity > 0
            else "blocked"
        )
        return {
            "dry_run": True,
            "decision": decision,
            "ok": decision == "ready",
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "ref_price": raw_price,
            "expected_fill_price": fill_price,
            "notional": notional,
            "equity": equity,
            "mode": self.settings.trading_mode,
            "broker": broker,
            "gate_ok": allowed,
            "gate_reason": gate_reason,
            "risk_ok": risk_ok,
            "risk_reason": cool_reason if cooling else risk_reason,
            "fee_bps": self.settings.paper_fee_bps if self.settings.trading_mode == "paper" else 0,
        }

    async def _update_position(self, symbol_id: int, side: str, qty: float, price: float) -> None:
        result = await self.db.execute(select(Position).where(Position.symbol_id == symbol_id))
        pos = result.scalar_one_or_none()
        signed = qty if side == "buy" else -qty
        if not pos:
            pos = Position(
                symbol_id=symbol_id,
                quantity=Decimal(str(signed)),
                avg_cost=Decimal(str(price)),
            )
            self.db.add(pos)
            return
        old_qty = float(pos.quantity)
        avg = float(pos.avg_cost or 0)
        close_qty = 0.0
        if old_qty > 0 and side == "sell":
            close_qty = min(qty, old_qty)
            pos.realized_pnl = Decimal(str(float(pos.realized_pnl or 0) + (price - avg) * close_qty))
        elif old_qty < 0 and side == "buy":
            close_qty = min(qty, abs(old_qty))
            pos.realized_pnl = Decimal(str(float(pos.realized_pnl or 0) + (avg - price) * close_qty))
        new_qty = old_qty + signed
        if side == "buy" and new_qty > 0:
            remain = max(old_qty, 0.0)
            pos.avg_cost = Decimal(str((avg * remain + qty * price) / max(new_qty, 1e-9)))
        elif side == "sell" and new_qty < 0:
            remain = max(-old_qty, 0.0)
            pos.avg_cost = Decimal(str((avg * remain + qty * price) / max(abs(new_qty), 1e-9)))
        pos.quantity = Decimal(str(new_qty))
        pos.updated_at = datetime.now(timezone.utc)
