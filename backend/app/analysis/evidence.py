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
    hit_se = float(np.sqrt(hit * (1.0 - hit) / n)) if n > 0 else 1.0
    hit_z = float((hit - 0.5) / hit_se) if hit_se > 0 else 0.0

    reasons: list[str] = []
    if n < min_samples:
        reasons.append(f"検証日数が足りない（{n}日 < {min_samples}日）")
    if hit + 1e-12 < min_hit_rate:
        reasons.append(f"方向的中 {hit:.1%} が下限 {min_hit_rate:.1%} 未満")

    ok = not reasons
    return {
        "ok": ok,
        "kind": "walk_forward_oos",
        "model": wf.get("model") or "ridge_ols_walk_forward",
        "horizon": wf.get("horizon") or "1d",
        "n_samples": n,
        "direction_hit_rate": hit,
        "hit_rate_se": hit_se,
        "hit_z": hit_z,
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


def merge_robust_evidence(
    short: dict[str, Any],
    long: dict[str, Any],
    *,
    min_expected_value: float = 0.0008,
    min_hit_z: float = 1.0,
) -> dict[str, Any]:
    """Require the short window and a longer confirm window to agree on edge."""
    reasons: list[str] = []
    if not short.get("ok"):
        reasons.append(f"直近60日: {short.get('block_reason') or '未通過'}")
    if not long.get("ok"):
        reasons.append(f"確認120日: {long.get('block_reason') or '未通過'}")
    short_ev = float(short.get("expected_value") or 0.0)
    long_ev = float(long.get("expected_value") or 0.0)
    if min(short_ev, long_ev) < min_expected_value:
        reasons.append(
            f"期待値 {min(short_ev, long_ev) * 10000:.1f}bps が下限 {min_expected_value * 10000:.1f}bps 未満"
        )
    if float(long.get("oos_strategy_return") or 0.0) <= 0:
        reasons.append("確認窓の手数料後リターンがマイナス")
    long_z = float(long.get("hit_z") or 0.0)
    if long_z < min_hit_z:
        reasons.append(f"確認窓の的中信頼度 z={long_z:.2f} < {min_hit_z:.2f}")

    out = dict(short)
    out["kind"] = "walk_forward_dual"
    out["confirm"] = {
        "n_samples": long.get("n_samples"),
        "direction_hit_rate": long.get("direction_hit_rate"),
        "expected_value": long_ev,
        "oos_strategy_return": long.get("oos_strategy_return"),
        "oos_sharpe": long.get("oos_sharpe"),
        "hit_z": long_z,
        "ok": long.get("ok"),
        "block_reason": long.get("block_reason"),
    }
    out["expected_value"] = min(short_ev, long_ev)
    out["oos_sharpe"] = min(float(short.get("oos_sharpe") or 0.0), float(long.get("oos_sharpe") or 0.0))
    out["direction_hit_rate"] = min(
        float(short.get("direction_hit_rate") or 0.0),
        float(long.get("direction_hit_rate") or 0.0),
    )
    out["hit_z"] = long_z
    out["ok"] = not reasons
    out["block_reason"] = None if not reasons else "; ".join(reasons)
    return out


def build_robust_evidence(
    df: pd.DataFrame,
    *,
    min_train: int = 40,
    short_points: int = 60,
    long_points: int = 120,
    min_hit_rate: float = 0.52,
    min_samples: int = 20,
    fee_bps: float = 5.0,
    min_expected_value: float = 0.0008,
    min_hit_z: float = 1.0,
) -> dict[str, Any]:
    short = build_ols_evidence(
        df,
        min_train=min_train,
        max_points=short_points,
        min_hit_rate=min_hit_rate,
        min_samples=min_samples,
        fee_bps=fee_bps,
    )
    long = build_ols_evidence(
        df,
        min_train=min_train,
        max_points=long_points,
        min_hit_rate=min_hit_rate,
        min_samples=min_samples,
        fee_bps=fee_bps,
    )
    return merge_robust_evidence(
        short,
        long,
        min_expected_value=min_expected_value,
        min_hit_z=min_hit_z,
    )
