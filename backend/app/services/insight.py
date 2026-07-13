"""Unified AI insight: price forecast, confidence, XAI, news summary, backtest, signal."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.accuracy import evaluate_walk_forward
from app.analysis.explain import (
    explain_linear_attribution,
    explain_sklearn_shap,
    explain_tree_importance,
    narrative_from_explanation,
)
from app.analysis.integrated import IntegratedAnalysisService
from app.backtest.engine import BacktestService
from app.llm.clients import NewsLLMService
from app.ml.ensemble import FEATURE_COLS, _prepare
from app.services.market_data import load_bars_df
from app.services.ingestion import DataIngestionService

# prediction.py uses inline list; keep local copy
OLS_FEATURES = ["return_1", "return_5", "ma_5", "ma_20", "vol_10", "volume_ma", "hl_range"]


def _normalize(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma < 1e-9] = 1.0
    return (X - mu) / sigma, mu, sigma


def _ols_bundle(df) -> dict[str, Any] | None:
    from app.services.prediction import _build_features, _dir_confidence, _ols_predict

    if df is None or len(df) < 40:
        return None
    feat = _build_features(df)
    if len(feat) < 20:
        return None
    X = feat[OLS_FEATURES].to_numpy(dtype=float)
    y_price = feat["target_price"].to_numpy(dtype=float)
    y_dir = feat["target_dir"].to_numpy(dtype=float)
    X_train, y_price_train, y_dir_train = X[:-1], y_price[:-1], y_dir[:-1]
    X_last = X[-1].copy()
    Xn, mu, sigma = _normalize(X_train)
    xl = (X_last - mu) / sigma
    pred_price = _ols_predict(Xn, y_price_train, xl)
    direction, confidence = _dir_confidence(Xn, y_dir_train, xl)
    last_close = float(feat.iloc[-1]["close"])
    explanation = explain_linear_attribution(
        feature_names=OLS_FEATURES,
        X_train=Xn,
        y_train=y_price_train,
        x_last=xl,
        predicted_value=pred_price,
        baseline=float(y_price_train.mean()),
    )
    return {
        "last_close": last_close,
        "predicted_price": float(pred_price),
        "predicted_return": float(pred_price / last_close - 1.0) if last_close else 0.0,
        "direction": direction,
        "confidence": float(confidence),
        "model": "ridge_ols_v1",
        "horizon": "1d",
        "explanation": explanation,
    }


def _ml_bundle(df) -> dict[str, Any]:
    from sklearn.ensemble import GradientBoostingRegressor

    prepared = _prepare(df)
    if len(prepared) < 60:
        return {"error": "insufficient data", "have": len(prepared)}
    X = prepared[FEATURE_COLS].to_numpy(dtype=float)
    y_reg = prepared["target_return"].to_numpy(dtype=float)
    X_train, y_train = X[:-1], y_reg[:-1]
    x_last = X[-1].copy()
    reg = GradientBoostingRegressor(n_estimators=80, max_depth=3, random_state=42)
    reg.fit(X_train, y_train)
    pred_ret = float(reg.predict(x_last.reshape(1, -1))[0])
    last_close = float(prepared.iloc[-1]["close"])
    shap_exp = explain_sklearn_shap(
        reg, feature_names=FEATURE_COLS, X_train=X_train, x_last=x_last
    )
    if shap_exp is None:
        shap_exp = explain_tree_importance(
            feature_names=FEATURE_COLS,
            importances=reg.feature_importances_,
            x_last=(x_last - X_train.mean(axis=0)) / (X_train.std(axis=0) + 1e-9),
            direction_sign=1.0 if pred_ret >= 0 else -1.0,
        )
    return {
        "predicted_return": pred_ret,
        "predicted_price": last_close * (1.0 + pred_ret),
        "direction": "up" if pred_ret >= 0 else "down",
        "model": "sklearn_gb",
        "explanation": shap_exp,
    }


def _signal_from_parts(
    *,
    direction: str,
    confidence: float,
    integrated_signal: str | None,
    integrated_score: float | None,
) -> dict[str, Any]:
    # Prefer integrated when available; else confidence-gated direction
    if integrated_signal in {"buy", "sell", "hold"}:
        action = integrated_signal
        source = "integrated"
        strength = abs(float(integrated_score or 0))
    elif confidence < 0.55:
        action = "hold"
        source = "ols_confidence_gate"
        strength = float(confidence)
    else:
        action = "buy" if direction == "up" else "sell"
        source = "ols_direction"
        strength = float(confidence)
    label_ja = {"buy": "買い", "sell": "売り", "hold": "様子見"}.get(action, action)
    return {
        "action": action,
        "label": label_ja,
        "source": source,
        "strength": strength,
        "confidence": float(confidence),
    }


class InsightService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(
        self,
        ticker: str,
        *,
        collect_news: bool = True,
        run_backtest: bool = True,
        persist_prediction: bool = True,
    ) -> dict[str, Any]:
        from app.services.prediction import PredictionService

        df = await load_bars_df(self.db, ticker, limit=300)
        if len(df) < 60:
            try:
                await DataIngestionService(self.db).ingest_bars(ticker, timeframe="1d", limit=300)
            except Exception:  # noqa: BLE001
                pass
            df = await load_bars_df(self.db, ticker, limit=300)
        if df.empty or len(df) < 40:
            return {"ok": False, "error": "insufficient bars", "ticker": ticker}

        ols = _ols_bundle(df)
        if not ols:
            return {"ok": False, "error": "prediction failed", "ticker": ticker}

        if persist_prediction:
            try:
                await PredictionService(self.db).predict(ticker)
            except Exception:  # noqa: BLE001
                pass

        ml = _ml_bundle(df)

        # Prefer SHAP tree explanation when available, else linear
        primary_explanation = ols["explanation"]
        if isinstance(ml, dict) and ml.get("explanation") and ml["explanation"].get("method") == "shap_tree":
            primary_explanation = ml["explanation"]
        elif isinstance(ml, dict) and ml.get("explanation"):
            # Keep OLS as primary but attach ML as secondary
            pass

        integrated = None
        try:
            integrated = await IntegratedAnalysisService(self.db).run(
                ticker, collect_news=collect_news
            )
        except Exception as e:  # noqa: BLE001
            integrated = {"error": str(e)}

        news_summary = ""
        articles = []
        if isinstance(integrated, dict) and "news" in integrated:
            articles = integrated["news"].get("articles") or []
            blob = "\n".join(
                f"- {a.get('title', '')}: {a.get('summary') or a.get('sentiment_label') or ''}"
                for a in articles[:6]
            )
            if blob.strip():
                news_summary = await NewsLLMService().summarize(
                    f"銘柄 {ticker} の関連ニュース:\n{blob}\n\n市場への示唆を日本語で要約してください。"
                )
            else:
                news_summary = "関連ニュースが不足しています。「ニュース」収集後に再実行してください。"
        else:
            news_summary = "ニュース統合に失敗しました。"

        bt_snap: dict[str, Any] = {}
        if run_backtest and len(df) >= 50:
            try:
                bt = BacktestService(self.db).run(df, engine="pandas", fast=10, slow=30)
                m = bt.get("metrics") or {}
                bt_snap = {
                    "engine": bt.get("engine"),
                    "strategy": bt.get("strategy"),
                    "metrics": {
                        "total_return": m.get("total_return"),
                        "buy_hold_return": m.get("buy_hold_return"),
                        "sharpe": m.get("sharpe"),
                        "max_drawdown": m.get("max_drawdown"),
                        "win_rate": m.get("win_rate"),
                        "trades": m.get("trades"),
                        "alpha_vs_buy_hold": m.get("alpha_vs_buy_hold"),
                    },
                }
            except Exception as e:  # noqa: BLE001
                bt_snap = {"error": str(e)}

        acc = evaluate_walk_forward(df, min_train=40, max_points=40)
        acc_metrics = acc.get("metrics") or {}

        int_signal = integrated.get("signal") if isinstance(integrated, dict) else None
        int_score = integrated.get("composite_score") if isinstance(integrated, dict) else None
        signal = _signal_from_parts(
            direction=ols["direction"],
            confidence=ols["confidence"],
            integrated_signal=int_signal,
            integrated_score=int_score,
        )
        narrative = narrative_from_explanation(
            primary_explanation, signal=signal["action"], confidence=ols["confidence"]
        )
        if isinstance(integrated, dict) and integrated.get("summary"):
            narrative.append(str(integrated["summary"]))

        return {
            "ok": True,
            "ticker": ticker,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "price": {
                "last_close": ols["last_close"],
                "predicted_price": ols["predicted_price"],
                "predicted_return": ols["predicted_return"],
                "direction": ols["direction"],
                "confidence": ols["confidence"],
                "model": ols["model"],
                "horizon": ols["horizon"],
                "ml_predicted_price": ml.get("predicted_price") if isinstance(ml, dict) else None,
                "ml_predicted_return": ml.get("predicted_return") if isinstance(ml, dict) else None,
            },
            "confidence": {
                "value": ols["confidence"],
                "label": (
                    "高"
                    if ols["confidence"] >= 0.7
                    else ("中" if ols["confidence"] >= 0.55 else "低")
                ),
                "note": "方向予測の確信度（OLS）。0.55未満は様子見ゲート。",
            },
            "signal": signal,
            "explanation": primary_explanation,
            "explanation_ml": ml.get("explanation") if isinstance(ml, dict) else None,
            "narrative": narrative,
            "news": {
                "summary": news_summary,
                "articles": articles[:6],
                "score": (integrated.get("scores") or {}).get("news")
                if isinstance(integrated, dict)
                else None,
            },
            "backtest": bt_snap,
            "accuracy": {
                "direction_hit_rate": acc_metrics.get("direction_hit_rate"),
                "mae": acc_metrics.get("mae"),
                "rmse": acc_metrics.get("rmse"),
                "model_total_return": acc_metrics.get("model_total_return"),
                "buy_hold_total_return": acc_metrics.get("buy_hold_total_return"),
                "n_samples": acc.get("n_samples"),
            },
            "integrated": {
                "scores": integrated.get("scores") if isinstance(integrated, dict) else None,
                "summary": integrated.get("summary") if isinstance(integrated, dict) else None,
            },
        }
