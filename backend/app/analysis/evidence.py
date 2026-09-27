"""OOS evidence bundle for predictions used as trading input."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.analysis.accuracy import evaluate_walk_forward


def summarize_walk_forward(
    wf: dict[str, Any],
    *,
    min_hit_rate: float = 0.52,
    min_samples: int = 20,
    fee_bps: float = 5.0,
) -> dict[str, Any]:
    """Turn a walk-forward result into a gateable evidence record."""
    metrics = wf.get("metrics") or {}
    series = wf.get("series") or []
    n = int(wf.get("n_samples") or len(series) or 0)
    hit = float(metrics.get("direction_hit_rate") or 0.0)
    mae = metrics.get("mae")
    rmse = metrics.get("rmse")

    fee = float(fee_bps) / 10000.0
    signed: list[float] = []
    wins: list[float] = []
    losses: list[float] = []
    for r in series:
        sign = 1.0 if r.get("predicted_direction") == "up" else -1.0
        net = sign * float(r.get("actual_return") or 0.0) - fee
        signed.append(net)
        if net > 0:
            wins.append(net)
        else:
            losses.append(net)

    strat = pd.Series(signed, dtype=float) if signed else pd.Series(dtype=float)
    equity = (1 + strat).cumprod() if len(strat) else pd.Series([1.0])
    strat_ret = float(equity.iloc[-1] - 1) if len(equity) else 0.0
    sharpe = (
        float(strat.mean() / (strat.std() + 1e-12) * np.sqrt(252)) if len(strat) > 2 else 0.0
    )
    expected_value = float(strat.mean()) if len(strat) else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    bh = float(metrics.get("buy_hold_total_return") or 0.0)

    reasons: list[str] = []
    if n < min_samples:
        reasons.append(f"oos_samples {n} < {min_samples}")
    if hit + 1e-12 < min_hit_rate:
        reasons.append(f"direction_hit_rate {hit:.3f} < {min_hit_rate:.3f}")

    ok = not reasons
    return {
        "ok": ok,
        "kind": "walk_forward_oos",
        "model": wf.get("model") or "ridge_ols_walk_forward",
        "horizon": wf.get("horizon") or "1d",
        "n_samples": n,
        "direction_hit_rate": hit,
        "mae": None if mae is None else float(mae),
        "rmse": None if rmse is None else float(rmse),
        "oos_strategy_return": strat_ret,
        "oos_sharpe": sharpe,
        "expected_value": expected_value,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "buy_hold_return": bh,
        "fee_bps": float(fee_bps),
        "min_hit_rate": float(min_hit_rate),
        "min_samples": int(min_samples),
        "block_reason": None if ok else "; ".join(reasons),
        "confusion": wf.get("confusion") or {},
    }


def build_ols_evidence(
    df: pd.DataFrame,
    *,
    min_train: int = 40,
    max_points: int = 60,
    min_hit_rate: float = 0.52,
    min_samples: int = 20,
    fee_bps: float = 5.0,
) -> dict[str, Any]:
    wf = evaluate_walk_forward(df, min_train=min_train, max_points=max_points)
    if wf.get("error") and not wf.get("series"):
        return {
            "ok": False,
            "kind": "walk_forward_oos",
            "model": "ridge_ols_walk_forward",
            "n_samples": 0,
            "direction_hit_rate": 0.0,
            "block_reason": str(wf.get("error")),
            "min_hit_rate": min_hit_rate,
            "min_samples": min_samples,
        }
    return summarize_walk_forward(
        wf,
        min_hit_rate=min_hit_rate,
        min_samples=min_samples,
        fee_bps=fee_bps,
    )
