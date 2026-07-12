"""Price direction prediction using numpy OLS (no sklearn dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MarketBar, Prediction, Symbol


@dataclass
class PredictionResult:
    ticker: str
    predicted_price: float
    direction: str
    confidence: float
    model_name: str
    horizon: str


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
    """Ridge-stabilized least squares."""
    n_features = X.shape[1]
    ones = np.ones((X.shape[0], 1))
    Xb = np.hstack([ones, X])
    xtx = Xb.T @ Xb + 1e-3 * np.eye(n_features + 1)
    xty = Xb.T @ y
    beta = np.linalg.solve(xtx, xty)
    return float(np.hstack([[1.0], x_last]) @ beta)


def _dir_confidence(X: np.ndarray, y_dir: np.ndarray, x_last: np.ndarray) -> tuple[str, float]:
    """Logistic-ish linear score via OLS on {0,1} labels, mapped to probability."""
    score = _ols_predict(X, y_dir.astype(float), x_last)
    # squash to (0,1)
    prob_up = 1.0 / (1.0 + np.exp(-4.0 * (score - 0.5)))
    if prob_up >= 0.5:
        return "up", float(prob_up)
    return "down", float(1.0 - prob_up)


class PredictionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _load_bars(self, ticker: str, limit: int = 250) -> pd.DataFrame:
        result = await self.db.execute(select(Symbol).where(Symbol.ticker == ticker))
        symbol = result.scalar_one_or_none()
        if not symbol:
            return pd.DataFrame()
        q = (
            select(MarketBar)
            .where(MarketBar.symbol_id == symbol.id, MarketBar.timeframe == "1d")
            .order_by(MarketBar.ts.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(q)).scalars().all()
        if not rows:
            return pd.DataFrame()
        data = [
            {
                "ts": r.ts,
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume or 0),
            }
            for r in reversed(rows)
        ]
        return pd.DataFrame(data)

    async def predict(self, ticker: str, horizon: str = "1d") -> PredictionResult | None:
        df = await self._load_bars(ticker)
        if len(df) < 40:
            return None
        feat = _build_features(df)
        feature_cols = ["return_1", "return_5", "ma_5", "ma_20", "vol_10", "volume_ma", "hl_range"]
        X = feat[feature_cols].values.astype(float)
        y_price = feat["target_price"].values.astype(float)
        y_dir = feat["target_dir"].values.astype(int)

        if len(X) < 20:
            return None
        X_train, y_price_train, y_dir_train = X[:-1], y_price[:-1], y_dir[:-1]
        X_last = X[-1].copy()

        # normalize features for stability
        mu = X_train.mean(axis=0)
        sigma = X_train.std(axis=0)
        sigma[sigma < 1e-9] = 1.0
        Xn = (X_train - mu) / sigma
        xl = (X_last - mu) / sigma

        pred_price = _ols_predict(Xn, y_price_train, xl)
        direction, confidence = _dir_confidence(Xn, y_dir_train, xl)

        result = await self.db.execute(select(Symbol).where(Symbol.ticker == ticker))
        symbol = result.scalar_one()
        rec = Prediction(
            symbol_id=symbol.id,
            model_name="ridge_ols_v1",
            horizon=horizon,
            predicted_at=datetime.now(timezone.utc),
            predicted_price=Decimal(str(round(pred_price, 4))),
            direction=direction,
            confidence=Decimal(str(round(confidence, 4))),
            features={c: float(X_last[i]) for i, c in enumerate(feature_cols)},
            meta={"train_rows": int(len(X_train))},
        )
        self.db.add(rec)
        await self.db.commit()
        await self.db.refresh(rec)

        return PredictionResult(
            ticker=ticker,
            predicted_price=pred_price,
            direction=direction,
            confidence=confidence,
            model_name="ridge_ols_v1",
            horizon=horizon,
        )
