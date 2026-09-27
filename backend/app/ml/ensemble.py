"""ML ensemble: sklearn / XGBoost / LightGBM / CatBoost for return & trade signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.analysis.technical import compute_all


@dataclass
class MLPrediction:
    model: str
    predicted_return: float
    direction: str
    confidence: float
    signal: str
    details: dict[str, Any]


FEATURE_COLS = [
    "return_1",
    "return_5",
    "sma_ratio",
    "rsi_14",
    "macd_hist",
    "atr_pct",
    "bb_width",
    "volume_z",
]


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    tech = compute_all(df)
    out = tech.copy()
    out["return_1"] = out["close"].pct_change()
    out["return_5"] = out["close"].pct_change(5)
    out["sma_ratio"] = out["close"] / out["sma_20"].replace(0, np.nan) - 1
    out["atr_pct"] = out["atr_14"] / out["close"].replace(0, np.nan)
    out["volume_z"] = (out["volume"] - out["volume"].rolling(20).mean()) / out["volume"].rolling(20).std()
    out["target_return"] = out["close"].pct_change().shift(-1)
    out["target_dir"] = (out["target_return"] > 0).astype(int)
    return out.dropna(subset=FEATURE_COLS + ["target_return", "target_dir"])


def _fit_predict_sklearn(X_train, y_reg, y_cls, X_last) -> MLPrediction:
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor

    reg = GradientBoostingRegressor(n_estimators=80, max_depth=3, random_state=42)
    clf = GradientBoostingClassifier(n_estimators=80, max_depth=3, random_state=42)
    reg.fit(X_train, y_reg)
    clf.fit(X_train, y_cls)
    pred_ret = float(reg.predict(X_last)[0])
    proba = float(np.max(clf.predict_proba(X_last)[0]))
    direction = "up" if clf.predict(X_last)[0] == 1 else "down"
    signal = "buy" if direction == "up" and pred_ret > 0.002 else ("sell" if direction == "down" and pred_ret < -0.002 else "hold")
    return MLPrediction("sklearn_gb", pred_ret, direction, proba, signal, {})


def _fit_predict_xgb(X_train, y_reg, y_cls, X_last) -> MLPrediction:
    from xgboost import XGBClassifier, XGBRegressor

    reg = XGBRegressor(n_estimators=100, max_depth=3, learning_rate=0.08, objective="reg:squarederror")
    clf = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.08, eval_metric="logloss")
    reg.fit(X_train, y_reg)
    clf.fit(X_train, y_cls)
    pred_ret = float(reg.predict(X_last)[0])
    proba = float(np.max(clf.predict_proba(X_last)[0]))
    direction = "up" if int(clf.predict(X_last)[0]) == 1 else "down"
    signal = "buy" if pred_ret > 0.002 else ("sell" if pred_ret < -0.002 else "hold")
    return MLPrediction("xgboost", pred_ret, direction, proba, signal, {})


def _fit_predict_lgbm(X_train, y_reg, y_cls, X_last) -> MLPrediction:
    from lightgbm import LGBMClassifier, LGBMRegressor

    reg = LGBMRegressor(n_estimators=100, max_depth=3, learning_rate=0.08, verbose=-1)
    clf = LGBMClassifier(n_estimators=100, max_depth=3, learning_rate=0.08, verbose=-1)
    reg.fit(X_train, y_reg)
    clf.fit(X_train, y_cls)
    pred_ret = float(reg.predict(X_last)[0])
    proba = float(np.max(clf.predict_proba(X_last)[0]))
    direction = "up" if int(clf.predict(X_last)[0]) == 1 else "down"
    signal = "buy" if pred_ret > 0.002 else ("sell" if pred_ret < -0.002 else "hold")
    return MLPrediction("lightgbm", pred_ret, direction, proba, signal, {})


def _fit_predict_catboost(X_train, y_reg, y_cls, X_last) -> MLPrediction:
    from catboost import CatBoostClassifier, CatBoostRegressor

    reg = CatBoostRegressor(iterations=100, depth=3, learning_rate=0.08, verbose=False)
    clf = CatBoostClassifier(iterations=100, depth=3, learning_rate=0.08, verbose=False)
    reg.fit(X_train, y_reg)
    clf.fit(X_train, y_cls)
    pred_ret = float(reg.predict(X_last)[0])
    proba = float(np.max(clf.predict_proba(X_last)[0]))
    direction = "up" if int(clf.predict(X_last)[0]) == 1 else "down"
    signal = "buy" if pred_ret > 0.002 else ("sell" if pred_ret < -0.002 else "hold")
    return MLPrediction("catboost", pred_ret, direction, proba, signal, {})


def evaluate_ml_ridge_walk_forward(
    df: pd.DataFrame,
    *,
    min_train: int = 50,
    max_points: int = 40,
) -> dict[str, Any]:
    """Expanding-window Ridge on the ensemble feature set (OOS, no GBM)."""
    prepared = _prepare(df)
    if len(prepared) < min_train + 5:
        return {
            "error": "insufficient data",
            "have": len(prepared),
            "n_samples": 0,
            "metrics": {},
        }
    start = max(min_train, len(prepared) - max_points)
    hits = 0
    total = 0
    signed: list[float] = []
    for i in range(start, len(prepared)):
        train = prepared.iloc[:i]
        row = prepared.iloc[i]
        X = train[FEATURE_COLS].to_numpy(dtype=float)
        y = train["target_return"].to_numpy(dtype=float)
        x_last = row[FEATURE_COLS].to_numpy(dtype=float)
        if not np.isfinite(X).all() or not np.isfinite(x_last).all():
            continue
        xtx = X.T @ X + 1e-3 * np.eye(X.shape[1])
        try:
            beta = np.linalg.solve(xtx, X.T @ y)
        except np.linalg.LinAlgError:
            continue
        pred = float(x_last @ beta)
        actual = float(row["target_return"])
        pred_dir = "up" if pred >= 0 else "down"
        actual_dir = "up" if actual >= 0 else "down"
        total += 1
        if pred_dir == actual_dir:
            hits += 1
        signed.append((1.0 if pred_dir == "up" else -1.0) * actual)
    if not total:
        return {"error": "no evaluable points", "n_samples": 0, "metrics": {}}
    strat = pd.Series(signed, dtype=float)
    equity = (1 + strat).cumprod()
    hit = hits / total
    return {
        "model": "ridge_on_ml_features_walk_forward",
        "n_samples": total,
        "metrics": {
            "direction_hit_rate": hit,
            "oos_strategy_return": float(equity.iloc[-1] - 1),
        },
    }


class MLEnsembleService:
    MODELS = ("sklearn", "xgboost", "lightgbm", "catboost")

    def predict(self, df: pd.DataFrame, models: list[str] | None = None) -> dict[str, Any]:
        prepared = _prepare(df)
        if len(prepared) < 60:
            return {"error": "insufficient data", "min_rows": 60, "have": len(prepared)}

        X = prepared[FEATURE_COLS].values.astype(float)
        y_reg = prepared["target_return"].values.astype(float)
        y_cls = prepared["target_dir"].values.astype(int)
        X_train, y_reg_train, y_cls_train = X[:-1], y_reg[:-1], y_cls[:-1]
        X_last = X[-1:].copy()

        selected = models or list(self.MODELS)
        results: list[MLPrediction] = []
        errors: dict[str, str] = {}
        runners = {
            "sklearn": _fit_predict_sklearn,
            "xgboost": _fit_predict_xgb,
            "lightgbm": _fit_predict_lgbm,
            "catboost": _fit_predict_catboost,
        }
        for name in selected:
            try:
                results.append(runners[name](X_train, y_reg_train, y_cls_train, X_last))
            except Exception as e:
                errors[name] = str(e)

        if not results:
            xtx = X_train.T @ X_train + 1e-3 * np.eye(X_train.shape[1])
            try:
                beta = np.linalg.solve(xtx, X_train.T @ y_reg_train)
                pred_ret = float(X_last[0] @ beta)
            except np.linalg.LinAlgError:
                return {"error": "all models failed", "details": errors}
            direction = "up" if pred_ret >= 0 else "down"
            signal = "buy" if pred_ret > 0.002 else ("sell" if pred_ret < -0.002 else "hold")
            results.append(
                MLPrediction(
                    "ridge_ml_features",
                    pred_ret,
                    direction,
                    0.5,
                    signal,
                    {"fallback": True, "errors": errors},
                )
            )
            errors["ensemble_fallback"] = "optional GBM libs missing; used numpy ridge"

        avg_ret = float(np.mean([r.predicted_return for r in results]))
        # upside / downside rates for reporting
        upside = max(avg_ret, 0.0)
        downside = abs(min(avg_ret, 0.0))
        votes = {"buy": 0, "sell": 0, "hold": 0}
        for r in results:
            votes[r.signal] += 1
        consensus = max(votes, key=votes.get)
        oos = evaluate_ml_ridge_walk_forward(df)
        oos_hit = float((oos.get("metrics") or {}).get("direction_hit_rate") or 0.0)
        return {
            "ensemble_return": avg_ret,
            "upside_rate": upside,
            "downside_rate": downside,
            "consensus_signal": consensus,
            "votes": votes,
            "confidence_kind": "in_sample_max_proba",
            "oos": oos,
            "evidence_ok": bool(oos.get("n_samples", 0) >= 20 and oos_hit >= 0.52),
            "note": "models[].confidence is in-sample. Use oos.metrics.direction_hit_rate for evidence.",
            "models": [
                {
                    "model": r.model,
                    "predicted_return": r.predicted_return,
                    "direction": r.direction,
                    "confidence": r.confidence,
                    "signal": r.signal,
                }
                for r in results
            ],
            "errors": errors,
        }
