"""Profit gate: trade only when OOS edge after costs is positive."""

from __future__ import annotations

from typing import Any

from app.analysis.session import lot_size_for, round_to_lot
from app.config import Settings, get_settings
from app.risk.manager import EnhancedRiskManager
from app.trading.expectancy import expected_yen, kelly_fraction, profit_score


def _predicted_return(last_close: float, predicted_price: float) -> float:
    if last_close <= 0:
        return 0.0
    return predicted_price / last_close - 1.0


def assess_edge(
    *,
    evidence: dict[str, Any] | None,
    direction: str,
    last_close: float,
    predicted_price: float,
    trend: str | None = None,
    rsi: float | None = None,
    equity: float = 10_000_000,
    settings: Settings | None = None,
    risk: EnhancedRiskManager | None = None,
    ticker: str | None = None,
    index_trend: str | None = None,
    mom_return: float | None = None,
) -> dict[str, Any]:
    """Return a sized buy/sell/hold plan. Hold unless after-fee OOS EV is positive."""
    s = settings or get_settings()
    evd = evidence or {}
    fee = (float(s.paper_fee_bps) + float(s.spread_bps)) / 10000.0
    pred_ret = _predicted_return(float(last_close or 0), float(predicted_price or 0))
    hit = float(evd.get("direction_hit_rate") or 0.0)
    oos_ret = float(evd.get("oos_strategy_return") or 0.0)
    sharpe = float(evd.get("oos_sharpe") or 0.0)
    expected = float(evd.get("expected_value") or 0.0)
    n = int(evd.get("n_samples") or 0)
    hit_z = float(evd.get("hit_z") or 0.0)
    lot = lot_size_for(ticker or "", s.jp_lot_size)

    reasons: list[str] = []
    if not evd.get("ok"):
        reasons.append(str(evd.get("block_reason") or "OOS evidence not ok"))
    if s.require_positive_oos_return and oos_ret <= 0:
        reasons.append(f"oos_strategy_return {oos_ret:.4f} <= 0 after fees")
    if sharpe < s.min_oos_sharpe:
        reasons.append(f"oos_sharpe {sharpe:.2f} < {s.min_oos_sharpe:.2f}")
    if expected < s.min_expected_value:
        reasons.append(f"expected_value {expected:.5f} < {s.min_expected_value:.5f}")
    min_move = 2.0 * fee + float(s.min_expected_value)
    if abs(pred_ret) < min_move:
        reasons.append(f"|predicted_return| {abs(pred_ret):.5f} < cost+edge {min_move:.5f}")
    if direction not in {"up", "down"}:
        reasons.append("direction missing")

    trend = (trend or "unknown").lower()
    if s.require_trend_align:
        if direction == "up" and trend == "downtrend":
            reasons.append("counter-trend long blocked")
        if direction == "down" and trend == "uptrend":
            reasons.append("counter-trend short blocked")
    idx = (index_trend or "unknown").lower()
    if s.require_index_align and idx in {"uptrend", "downtrend"}:
        if direction == "up" and idx == "downtrend":
            reasons.append("index downtrend blocks long")
        if direction == "down" and idx == "uptrend":
            reasons.append("index uptrend blocks short")
    if s.require_momentum_align and mom_return is not None:
        if direction == "up" and mom_return <= 0:
            reasons.append("20d momentum not up")
        if direction == "down" and mom_return >= 0:
            reasons.append("20d momentum not down")
    if rsi is not None:
        if direction == "up" and rsi >= s.rsi_overbought:
            reasons.append(f"RSI {rsi:.1f} overbought")
        if direction == "down" and rsi <= s.rsi_oversold:
            reasons.append(f"RSI {rsi:.1f} oversold")

    ok = not reasons
    action = "hold"
    if ok and direction == "up":
        action = "buy"
    elif ok and direction == "down":
        action = "sell"

    scale = 0.0
    if ok and s.min_expected_value > 0:
        scale = min(1.5, max(0.25, expected / s.min_expected_value))
    qty = 0.0
    price = float(last_close or 0)
    kelly = kelly_fraction(
        hit,
        evd.get("avg_win"),
        evd.get("avg_loss"),
        fraction=float(s.kelly_fraction),
    )
    if action in {"buy", "sell"} and price > 0 and risk is not None:
        base = risk.position_size(
            equity=equity,
            price=price,
            risk_per_trade_pct=s.risk_per_trade_pct,
        )
        qty = float(max(0.0, base * scale))
        if kelly > 0:
            qty = min(qty, equity * kelly / price)
        qty = round_to_lot(qty, lot)
        if qty < lot:
            reasons.append(f"qty below lot {lot}")
            ok = False
            action = "hold"
            qty = 0.0
    yen = expected_yen(qty, price, expected) if qty and price else 0.0

    return {
        "ok": ok,
        "action": action,
        "reasons": reasons,
        "block_reason": None if ok else "; ".join(reasons),
        "predicted_return": pred_ret,
        "expected_value": expected,
        "expected_yen": round(yen, 2),
        "profit_score": round(profit_score({"expected_value": expected, "oos_sharpe": sharpe, "predicted_return": pred_ret}), 8),
        "kelly_fraction": round(kelly, 6),
        "oos_strategy_return": oos_ret,
        "oos_sharpe": sharpe,
        "direction_hit_rate": hit,
        "hit_z": round(hit_z, 3),
        "n_samples": n,
        "trend": trend,
        "index_trend": idx,
        "mom_return": mom_return,
        "lot": lot,
        "rsi": rsi,
        "size_scale": scale,
        "suggested_qty": round(qty, 4),
        "equity": equity,
        "note": "No guaranteed profit. Dual-window OOS, costs, lot, and regime must agree.",
    }
