"""Rank positive-EV names and lock open profits. Does not guarantee profit."""

from __future__ import annotations

from typing import Any


def kelly_fraction(
    hit_rate: float,
    avg_win: float | None,
    avg_loss: float | None,
    fraction: float = 0.25,
    cap: float = 0.05,
) -> float:
    """Quarter-Kelly from OOS win/loss. Zero when inputs are unusable."""
    p = float(hit_rate or 0.0)
    win = float(avg_win or 0.0)
    loss = abs(float(avg_loss or 0.0))
    if p <= 0.0 or p >= 1.0 or win <= 0.0 or loss <= 0.0 or fraction <= 0.0:
        return 0.0
    b = win / loss
    f_star = p - (1.0 - p) / b
    return float(max(0.0, min(cap, f_star * fraction)))


def profit_score(plan: dict[str, Any]) -> float:
    ev = float(plan.get("expected_value") or 0.0)
    sharpe = float(plan.get("oos_sharpe") or 0.0)
    move = abs(float(plan.get("predicted_return") or 0.0))
    if ev <= 0.0:
        return 0.0
    return ev * max(sharpe, 0.05) * max(move, 1e-4)


def expected_yen(quantity: float, price: float, expected_value: float) -> float:
    return float(quantity) * float(price) * float(expected_value)


def compute_trail(
    *,
    quantity: float,
    avg_cost: float,
    last: float,
    stop: float | None,
    sl_pct: float,
    trail_pct: float,
    lock_r: float = 1.0,
) -> tuple[float | None, str]:
    """Raise (long) or lower (short) the stop after +1R, then trail."""
    if quantity == 0 or avg_cost <= 0 or last <= 0 or sl_pct <= 0:
        return stop, "flat"
    r = avg_cost * sl_pct
    if quantity > 0:
        profit = last - avg_cost
        new_stop = stop
        reason = "hold"
        if profit >= r * lock_r:
            be = avg_cost * 1.0005
            new_stop = max(stop or 0.0, be)
            reason = "lock_breakeven"
        if profit >= r * (lock_r + 0.5):
            trail = last * (1.0 - trail_pct)
            new_stop = max(new_stop or 0.0, trail)
            reason = "trail"
        return new_stop, reason
    profit = avg_cost - last
    new_stop = stop
    reason = "hold"
    if profit >= r * lock_r:
        be = avg_cost * 0.9995
        new_stop = min(stop if stop is not None else 1e18, be)
        reason = "lock_breakeven"
    if profit >= r * (lock_r + 0.5):
        trail = last * (1.0 + trail_pct)
        new_stop = min(new_stop if new_stop is not None else 1e18, trail)
        reason = "trail"
    return new_stop, reason


def allocate_book(
    actionable: list[dict[str, Any]],
    *,
    equity: float,
    risk_per_trade_pct: float,
    max_new_trades: int,
    max_position_pct: float,
    stop_loss_pct: float,
    open_tickers: set[str] | None = None,
) -> dict[str, Any]:
    """Concentrate daily risk on the highest OOS EV×Sharpe×move names."""
    held = open_tickers or set()
    ranked: list[tuple[float, dict[str, Any]]] = []
    skipped_open: list[str] = []
    for row in actionable:
        ticker = str(row.get("ticker") or "")
        plan = row.get("plan") or {}
        if ticker in held:
            skipped_open.append(ticker)
            continue
        if not plan.get("ok") or plan.get("action") not in {"buy", "sell"}:
            continue
        score = profit_score(plan)
        if score <= 0:
            continue
        ranked.append((score, row))
    ranked.sort(key=lambda x: x[0], reverse=True)
    cap = max(1, int(max_new_trades))
    top = ranked[:cap]
    total_score = sum(s for s, _ in top) or 1.0
    daily_risk = float(equity) * float(risk_per_trade_pct) * float(cap)
    picks: list[dict[str, Any]] = []
    for score, row in top:
        plan = row.get("plan") or {}
        price = float(row.get("last_close") or 0.0)
        weight = score / total_score
        risk_yen = daily_risk * weight
        qty = risk_yen / (price * stop_loss_pct) if price > 0 and stop_loss_pct > 0 else 0.0
        suggested = float(plan.get("suggested_qty") or 0.0)
        if suggested > 0:
            qty = min(qty, suggested)
        if price > 0 and max_position_pct > 0:
            qty = min(qty, (equity * max_position_pct) / price)
        ev = float(plan.get("expected_value") or 0.0)
        yen = expected_yen(qty, price, ev)
        picks.append(
            {
                "ticker": row.get("ticker"),
                "action": plan.get("action"),
                "score": round(score, 8),
                "weight": round(weight, 4),
                "quantity": round(max(0.0, qty), 4),
                "last_close": price,
                "expected_value": ev,
                "expected_yen": round(yen, 2),
                "oos_sharpe": plan.get("oos_sharpe"),
                "predicted_return": plan.get("predicted_return"),
                "plan": plan,
            }
        )
    return {
        "picks": picks,
        "skipped_open": skipped_open,
        "candidates": len(ranked),
        "expected_portfolio_yen": round(sum(float(p["expected_yen"]) for p in picks), 2),
        "daily_risk_budget": round(daily_risk, 2),
        "equity": equity,
        "note": "OOS EV が正の銘柄にリスク予算を寄せる。利益は保証しない。",
    }
