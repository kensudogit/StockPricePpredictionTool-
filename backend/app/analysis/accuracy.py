"""Walk-forward prediction accuracy evaluation for visualization."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FEATURE_COLS = ["return_1", "return_5", "ma_5", "ma_20", "vol_10", "volume_ma", "hl_range"]


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["return_1"] = out["close"].pct_change()
    out["return_5"] = out["close"].pct_change(5)
    out["ma_5"] = out["close"].rolling(5).mean()
    out["ma_20"] = out["close"].rolling(20).mean()
    out["vol_10"] = out["return_1"].rolling(10).std()
    out["volume_ma"] = out["volume"].rolling(5).mean()
    out["hl_range"] = (out["high"] - out["low"]) / out["close"].replace(0, np.nan)
    out["target_price"] = out["close"].shift(-1)
    out["target_dir"] = (out["close"].shift(-1) > out["close"]).astype(int)
    return out.dropna()


def _ols_predict(X: np.ndarray, y: np.ndarray, x_last: np.ndarray) -> float:
    n_features = X.shape[1]
    ones = np.ones((X.shape[0], 1))
    xb = np.hstack([ones, X])
    xtx = xb.T @ xb + 1e-3 * np.eye(n_features + 1)
    xty = xb.T @ y
    beta = np.linalg.solve(xtx, xty)
    return float(np.hstack([[1.0], x_last]) @ beta)


def _dir_confidence(X: np.ndarray, y_dir: np.ndarray, x_last: np.ndarray) -> tuple[str, float]:
    score = _ols_predict(X, y_dir.astype(float), x_last)
    prob_up = 1.0 / (1.0 + np.exp(-4.0 * (score - 0.5)))
    if prob_up >= 0.5:
        return "up", float(prob_up)
    return "down", float(1.0 - prob_up)


def evaluate_walk_forward(
    df: pd.DataFrame,
    *,
    min_train: int = 40,
    max_points: int = 80,
) -> dict[str, Any]:
    """Expanding-window OLS: predict next-day price/direction vs actual."""
    if df is None or df.empty or len(df) < min_train + 5:
        return {
            "error": "insufficient data",
            "min_rows": min_train + 5,
            "have": 0 if df is None else len(df),
            "metrics": {},
            "series": [],
            "confusion": {},
        }

    feat = _build_features(df)
    if len(feat) < min_train + 2:
        return {
            "error": "insufficient features after dropna",
            "have": len(feat),
            "metrics": {},
            "series": [],
            "confusion": {},
        }

    start = max(min_train, len(feat) - max_points)
    rows: list[dict[str, Any]] = []
    abs_err: list[float] = []
    sq_err: list[float] = []
    hits = 0
    total = 0
    tp = tn = fp = fn = 0

    for i in range(start, len(feat)):
        train = feat.iloc[:i]
        row = feat.iloc[i]
        X = train[FEATURE_COLS].to_numpy(dtype=float)
        y_price = train["target_price"].to_numpy(dtype=float)
        y_dir = train["target_dir"].to_numpy(dtype=float)
        x_last = row[FEATURE_COLS].to_numpy(dtype=float)
        if np.any(~np.isfinite(X)) or np.any(~np.isfinite(x_last)):
            continue
        try:
            pred_price = _ols_predict(X, y_price, x_last)
            direction, confidence = _dir_confidence(X, y_dir, x_last)
        except Exception:  # noqa: BLE001
            continue

        actual_price = float(row["target_price"])
        actual_close = float(row["close"])
        actual_return = (actual_price / actual_close) - 1.0 if actual_close else 0.0
        pred_return = (pred_price / actual_close) - 1.0 if actual_close else 0.0
        actual_dir = "up" if float(row["target_dir"]) >= 0.5 else "down"
        correct = direction == actual_dir

        err = pred_price - actual_price
        abs_err.append(abs(err))
        sq_err.append(err * err)
        total += 1
        if correct:
            hits += 1
        if direction == "up" and actual_dir == "up":
            tp += 1
        elif direction == "down" and actual_dir == "down":
            tn += 1
        elif direction == "up" and actual_dir == "down":
            fp += 1
        else:
            fn += 1

        ts = row["ts"] if "ts" in feat.columns else feat.index[i]
        rows.append(
            {
                "ts": str(ts)[:19],
                "close": actual_close,
                "predicted_price": float(pred_price),
                "actual_price": actual_price,
                "predicted_return": float(pred_return),
                "actual_return": float(actual_return),
                "predicted_direction": direction,
                "actual_direction": actual_dir,
                "correct": correct,
                "confidence": float(confidence),
                "error": float(err),
            }
        )

    if not rows:
        return {"error": "no evaluable points", "metrics": {}, "series": [], "confusion": {}}

    mae = float(np.mean(abs_err))
    rmse = float(np.sqrt(np.mean(sq_err)))
    hit_rate = hits / total if total else 0.0
    signed = []
    for r in rows:
        sign = 1.0 if r["predicted_direction"] == "up" else -1.0
        signed.append(sign * r["actual_return"])
    strat = pd.Series(signed, dtype=float)
    equity = (1 + strat).cumprod()
    bh = pd.Series([r["actual_return"] for r in rows], dtype=float)
    bh_equity = (1 + bh).cumprod()

    for i, r in enumerate(rows):
        r["model_equity"] = float(equity.iloc[i])
        r["buy_hold_equity"] = float(bh_equity.iloc[i])

    return {
        "model": "ridge_ols_walk_forward",
        "horizon": "1d",
        "n_samples": total,
        "metrics": {
            "direction_hit_rate": hit_rate,
            "mae": mae,
            "rmse": rmse,
            "mean_abs_return_error": float(
                np.mean([abs(r["predicted_return"] - r["actual_return"]) for r in rows])
            ),
            "model_total_return": float(equity.iloc[-1] - 1),
            "buy_hold_total_return": float(bh_equity.iloc[-1] - 1),
            "avg_confidence": float(np.mean([r["confidence"] for r in rows])),
        },
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "series": rows,
    }
