"""Unit tests for walk-forward accuracy and integrated scoring (no DB)."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.analysis.accuracy import evaluate_walk_forward
from app.analysis.integrated_scoring import combine_scores, score_fundamentals, score_news, score_technical


def _synthetic_ohlcv(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0.05, 1.0, n))
    high = close + rng.uniform(0.2, 1.5, n)
    low = close - rng.uniform(0.2, 1.5, n)
    open_ = close + rng.normal(0, 0.3, n)
    volume = rng.integers(1000, 5000, n).astype(float)
    ts = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"ts": ts, "open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


class TestAccuracyWalkForward(unittest.TestCase):
    def test_evaluate_returns_metrics_and_series(self):
        df = _synthetic_ohlcv(100)
        out = evaluate_walk_forward(df, min_train=40, max_points=30)
        self.assertNotIn("error", out)
        self.assertGreater(out["n_samples"], 5)
        self.assertIn("direction_hit_rate", out["metrics"])
        self.assertEqual(len(out["series"]), out["n_samples"])
        self.assertIn("model_equity", out["series"][-1])
        self.assertIn("buy_hold_equity", out["series"][-1])

    def test_insufficient_data(self):
        df = _synthetic_ohlcv(20)
        out = evaluate_walk_forward(df, min_train=40)
        self.assertIn("error", out)


class TestIntegratedScoring(unittest.TestCase):
    def test_technical_rsi_extremes(self):
        score_hi, _ = score_technical({"trend": "uptrend", "rsi_14": 80, "macd": 1, "macd_signal": 0.5, "adx": 30})
        score_lo, _ = score_technical({"trend": "downtrend", "rsi_14": 20, "macd": -1, "macd_signal": -0.5, "adx": 30})
        self.assertIsInstance(score_hi, float)
        self.assertIsInstance(score_lo, float)

    def test_fundamentals_and_news(self):
        f, reasons = score_fundamentals({"per": 8, "pbr": 0.8, "roe": 0.15, "operating_margin": 0.1})
        self.assertGreater(f, 0)
        self.assertTrue(reasons)
        n, n_reasons, meta = score_news(
            [
                {"title": "好決算", "sentiment": 0.6, "sentiment_label": "positive"},
                {"title": "懸念", "sentiment": -0.4, "sentiment_label": "negative"},
            ]
        )
        self.assertEqual(meta["count"], 2)
        self.assertTrue(n_reasons)

    def test_combine_signal(self):
        c, signal, strength = combine_scores(0.6, 0.4, 0.3)
        self.assertEqual(signal, "buy")
        self.assertGreater(strength, 0)
        _, hold, _ = combine_scores(0.05, 0.0, -0.05)
        self.assertEqual(hold, "hold")


if __name__ == "__main__":
    unittest.main()
