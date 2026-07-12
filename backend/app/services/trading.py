"""Trading decision + paper order execution + risk checks."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Order, Position, RiskEvent, TradingSignal
from app.risk.manager import EnhancedRiskManager


class RiskManager(EnhancedRiskManager):
    """Backward-compatible alias used by OrderService."""

    async def check_order(
        self,
        *,
        equity: float,
        order_notional: float,
        daily_pnl: float,
    ) -> tuple[bool, str]:
        return await super().check_order(
            equity=equity,
            order_notional=order_notional,
            daily_pnl=daily_pnl,
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
    ) -> TradingSignal:
        if confidence < min_confidence:
            signal_type = "hold"
            rationale = f"Confidence {confidence:.2f} below threshold {min_confidence}"
        elif direction == "up":
            signal_type = "buy"
            rationale = f"Model expects upside with confidence {confidence:.2f}"
        else:
            signal_type = "sell"
            rationale = f"Model expects downside with confidence {confidence:.2f}"

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

        notional = quantity * price
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
            avg_fill_price=Decimal(str(price)) if mode == "paper" else None,
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(order)
        signal.status = "executed"
        if mode == "paper":
            await self._update_position(signal.symbol_id, signal.signal_type, quantity, price)
            await self.db.flush()
            pos = (
                await self.db.execute(select(Position).where(Position.symbol_id == signal.symbol_id))
            ).scalar_one_or_none()
            if pos and signal.signal_type == "buy":
                await self.risk.attach_stops(
                    position_id=pos.id,
                    symbol_id=signal.symbol_id,
                    side="buy",
                    entry_price=price,
                    quantity=quantity,
                )
        await self.db.commit()
        await self.db.refresh(order)
        return order

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
        new_qty = float(pos.quantity) + signed
        if side == "buy" and new_qty != 0:
            # average cost for buys
            old_cost = float(pos.avg_cost or 0) * float(pos.quantity)
            pos.avg_cost = Decimal(str((old_cost + qty * price) / max(new_qty, 1e-9)))
        pos.quantity = Decimal(str(new_qty))
        pos.updated_at = datetime.now(timezone.utc)
