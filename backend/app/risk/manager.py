"""Mandatory risk controls: stop-loss, take-profit, sizing, max loss, max positions, leverage."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Position, RiskEvent, RiskOrder


class RiskPolicy:
    def __init__(self) -> None:
        s = get_settings()
        self.max_position_pct = s.max_position_pct
        self.max_daily_loss_pct = s.max_daily_loss_pct
        self.max_order_notional = s.max_order_notional
        self.default_stop_loss_pct = s.default_stop_loss_pct
        self.default_take_profit_pct = s.default_take_profit_pct
        self.max_open_positions = s.max_open_positions
        self.max_leverage = s.max_leverage
        self.max_portfolio_loss_pct = s.max_portfolio_loss_pct


class EnhancedRiskManager:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.policy = RiskPolicy()

    def position_size(
        self,
        *,
        equity: float,
        price: float,
        stop_loss_pct: float | None = None,
        risk_per_trade_pct: float = 0.01,
    ) -> float:
        """Risk-based sizing: risk budget / per-share risk."""
        stop = stop_loss_pct or self.policy.default_stop_loss_pct
        risk_budget = equity * risk_per_trade_pct
        per_share_risk = price * stop
        if per_share_risk <= 0:
            return 0.0
        qty = risk_budget / per_share_risk
        max_by_pct = (equity * self.policy.max_position_pct) / price
        max_by_notional = self.policy.max_order_notional / price
        return float(max(0.0, min(qty, max_by_pct, max_by_notional)))

    async def check_order(
        self,
        *,
        equity: float,
        order_notional: float,
        daily_pnl: float,
        leverage: float = 1.0,
        opening_new: bool = True,
    ) -> tuple[bool, str]:
        if leverage > self.policy.max_leverage:
            await self._log("leverage_limit", "warning", f"Leverage {leverage} > max {self.policy.max_leverage}")
            return False, "Leverage limit exceeded"
        if order_notional > self.policy.max_order_notional:
            return False, "Order notional exceeds max"
        if equity > 0 and order_notional / equity > self.policy.max_position_pct:
            return False, "Position size exceeds max % of equity"
        if equity > 0 and daily_pnl < 0 and abs(daily_pnl) / equity > self.policy.max_daily_loss_pct:
            await self._log("daily_loss_limit", "critical", "Daily loss limit breached")
            return False, "Daily loss limit breached"
        if equity > 0 and daily_pnl < 0 and abs(daily_pnl) / equity > self.policy.max_portfolio_loss_pct:
            await self._log("portfolio_loss_limit", "critical", "Max portfolio loss breached")
            return False, "Max portfolio loss breached"
        if opening_new:
            open_count = (
                await self.db.execute(select(func.count()).select_from(Position).where(Position.quantity != 0))
            ).scalar_one()
            if open_count >= self.policy.max_open_positions:
                return False, f"Max open positions ({self.policy.max_open_positions}) reached"
        return True, "ok"

    async def attach_stops(
        self,
        *,
        position_id: int,
        symbol_id: int,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
    ) -> dict:
        sl_pct = stop_loss_pct or self.policy.default_stop_loss_pct
        tp_pct = take_profit_pct or self.policy.default_take_profit_pct
        if side == "buy":
            stop = entry_price * (1 - sl_pct)
            take = entry_price * (1 + tp_pct)
        else:
            stop = entry_price * (1 + sl_pct)
            take = entry_price * (1 - tp_pct)

        pos = (
            await self.db.execute(select(Position).where(Position.id == position_id))
        ).scalar_one_or_none()
        if pos:
            pos.stop_loss = Decimal(str(round(stop, 6)))
            pos.take_profit = Decimal(str(round(take, 6)))

        for kind, price in (("stop_loss", stop), ("take_profit", take)):
            self.db.add(
                RiskOrder(
                    position_id=position_id,
                    symbol_id=symbol_id,
                    order_kind=kind,
                    trigger_price=Decimal(str(round(price, 6))),
                    quantity=Decimal(str(quantity)),
                    status="active",
                )
            )
        await self.db.commit()
        return {"stop_loss": stop, "take_profit": take}

    async def evaluate_marks(self, symbol_id: int, last_price: float) -> list[dict]:
        """Trigger stop/take when mark price crosses levels."""
        rows = (
            await self.db.execute(
                select(RiskOrder).where(
                    RiskOrder.symbol_id == symbol_id,
                    RiskOrder.status == "active",
                )
            )
        ).scalars().all()
        triggered = []
        for ro in rows:
            px = float(ro.trigger_price)
            hit = False
            if ro.order_kind == "stop_loss" and last_price <= px:
                hit = True
            if ro.order_kind == "take_profit" and last_price >= px:
                hit = True
            if hit:
                ro.status = "triggered"
                ro.triggered_at = datetime.now(timezone.utc)
                triggered.append(
                    {
                        "id": ro.id,
                        "kind": ro.order_kind,
                        "trigger_price": px,
                        "last_price": last_price,
                    }
                )
                await self._log(
                    ro.order_kind,
                    "info",
                    f"{ro.order_kind} triggered at {last_price}",
                    {"risk_order_id": ro.id},
                )
        if triggered:
            await self.db.commit()
        return triggered

    async def _log(self, event_type: str, severity: str, message: str, details: dict | None = None) -> None:
        self.db.add(
            RiskEvent(
                event_type=event_type,
                severity=severity,
                message=message,
                details=details or {},
            )
        )
        await self.db.commit()
