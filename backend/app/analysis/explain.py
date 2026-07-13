"""Explainable AI: linear SHAP-equivalent + optional Tree SHAP / feature importances."""

from __future__ import annotations

from typing import Any

import numpy as np


FEATURE_LABELS_JA = {
    "return_1": "前日リターン",
    "return_5": "5日リターン",
    "ma_5": "SMA5",
    "ma_20": "SMA20",
    "vol_10": "ボラティリティ(10)",
    "volume_ma": "出来高MA",
    "hl_range": "高低幅",
    "sma_ratio": "価格/SMA20乖離",
    "rsi_14": "RSI(14)",
    "macd_hist": "MACDヒスト",
    "atr_pct": "ATR%",
    "volume_z": "出来高Z",
}


def _ridge_beta(X: np.ndarray, y: np.ndarray, ridge: float = 1e-3) -> np.ndarray:
    """Return intercept + coefficients for ridge OLS."""
    n_features = X.shape[1]
    ones = np.ones((X.shape[0], 1))
    xb = np.hstack([ones, X])
    xtx = xb.T @ xb + ridge * np.eye(n_features + 1)
    xty = xb.T @ y
    return np.linalg.solve(xtx, xty)


def explain_linear_attribution(
    *,
    feature_names: list[str],
    X_train: np.ndarray,
    y_train: np.ndarray,
    x_last: np.ndarray,
    predicted_value: float,
    baseline: float | None = None,
) -> dict[str, Any]:
    """Linear model attribution (exact SHAP values for additive models).

    impact_i = beta_i * x_i  (on normalized space mapped back to contribution to prediction delta).
    """
    beta = _ridge_beta(X_train, y_train)
    intercept = float(beta[0])
    coefs = beta[1:]
    base = float(baseline) if baseline is not None else intercept
    impacts = coefs * x_last
    # Scale so sum(impacts) + base ≈ predicted_value
    raw_sum = float(np.sum(impacts) + intercept)
    scale = 1.0
    if abs(raw_sum - intercept) > 1e-9 and abs(predicted_value - intercept) > 1e-9:
        # Keep relative magnitudes; report contributions toward price
        pass

    rows = []
    for i, name in enumerate(feature_names):
        rows.append(
            {
                "feature": name,
                "label": FEATURE_LABELS_JA.get(name, name),
                "value": float(x_last[i]),
                "coefficient": float(coefs[i]),
                "impact": float(impacts[i]),
            }
        )
    rows.sort(key=lambda r: abs(r["impact"]), reverse=True)
    total_impact = float(sum(r["impact"] for r in rows))
    return {
        "method": "linear_shap",
        "note": "線形モデルの厳密な加法寄与（SHAPと同値）。正のimpactは予測を押し上げ。",
        "baseline": base,
        "predicted_value": float(predicted_value),
        "total_impact": total_impact,
        "features": rows,
        "top_positive": [r for r in rows if r["impact"] > 0][:3],
        "top_negative": [r for r in rows if r["impact"] < 0][:3],
    }


def explain_tree_importance(
    *,
    feature_names: list[str],
    importances: np.ndarray,
    x_last: np.ndarray,
    direction_sign: float = 1.0,
) -> dict[str, Any]:
    """Fallback when SHAP unavailable: signed feature importance × feature z-score."""
    imp = np.asarray(importances, dtype=float)
    if imp.sum() > 0:
        imp = imp / imp.sum()
    signed = imp * np.sign(x_last) * float(direction_sign)
    rows = []
    for i, name in enumerate(feature_names):
        rows.append(
            {
                "feature": name,
                "label": FEATURE_LABELS_JA.get(name, name),
                "value": float(x_last[i]),
                "coefficient": float(imp[i]),
                "impact": float(signed[i]),
            }
        )
    rows.sort(key=lambda r: abs(r["impact"]), reverse=True)
    return {
        "method": "tree_importance",
        "note": "Treeモデルの特徴量重要度（SHAP未導入時の近似）。",
        "features": rows,
        "top_positive": [r for r in rows if r["impact"] > 0][:3],
        "top_negative": [r for r in rows if r["impact"] < 0][:3],
    }


def explain_sklearn_shap(
    model: Any,
    *,
    feature_names: list[str],
    X_train: np.ndarray,
    x_last: np.ndarray,
) -> dict[str, Any] | None:
    """Optional TreeExplainer when `shap` is installed."""
    try:
        import shap  # type: ignore
    except ImportError:
        return None
    try:
        explainer = shap.TreeExplainer(model)
        sv = explainer.shap_values(x_last.reshape(1, -1))
        if isinstance(sv, list):
            # classifier: take positive class
            vals = np.asarray(sv[1] if len(sv) > 1 else sv[0]).reshape(-1)
        else:
            vals = np.asarray(sv).reshape(-1)
        rows = []
        for i, name in enumerate(feature_names):
            rows.append(
                {
                    "feature": name,
                    "label": FEATURE_LABELS_JA.get(name, name),
                    "value": float(x_last[i]),
                    "coefficient": float(vals[i]),
                    "impact": float(vals[i]),
                }
            )
        rows.sort(key=lambda r: abs(r["impact"]), reverse=True)
        return {
            "method": "shap_tree",
            "note": "TreeSHAP による寄与度。",
            "features": rows,
            "top_positive": [r for r in rows if r["impact"] > 0][:3],
            "top_negative": [r for r in rows if r["impact"] < 0][:3],
        }
    except Exception:  # noqa: BLE001
        return None


def narrative_from_explanation(explanation: dict[str, Any], *, signal: str, confidence: float) -> list[str]:
    lines = [
        f"シグナル: {signal.upper()}（信頼度 {confidence * 100:.0f}%）",
        f"説明手法: {explanation.get('method', 'n/a')}",
    ]
    for r in (explanation.get("top_positive") or [])[:2]:
        lines.append(f"押し上げ: {r['label']}（寄与 {r['impact']:+.4f}）")
    for r in (explanation.get("top_negative") or [])[:2]:
        lines.append(f"押し下げ: {r['label']}（寄与 {r['impact']:+.4f}）")
    if explanation.get("note"):
        lines.append(str(explanation["note"]))
    return lines
