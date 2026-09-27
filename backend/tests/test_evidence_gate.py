"""OOS evidence and live-order gate (no network)."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.analysis.accuracy import evaluate_walk_forward
from app.analysis.evidence import build_ols_evidence, summarize_walk_forward
from app.backtest.engine import BacktestService, run_ols_signal_backtest
from app.config import Settings
from app.ml.ensemble import MLEnsembleService, evaluate_ml_ridge_walk_forward
from app.trading.gate import can_place, live_trading_allowed, live_venue


def _ohlcv(n: int = 120, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.02, 1.0, n))
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": rng.integers(1000, 4000, n).astype(float),
        }
    )


class TestEvidence(unittest.TestCase):
    def test_summarize_marks_insufficient_samples(self):
        wf = evaluate_walk_forward(_ohlcv(80), min_train=40, max_points=5)
        ev = summarize_walk_forward(wf, min_samples=20, min_hit_rate=0.52)
        self.assertFalse(ev["ok"])
        self.assertIn("oos_samples", ev["block_reason"] or "")

    def test_build_ols_evidence_has_hit_rate(self):
        ev = build_ols_evidence(_ohlcv(120), min_samples=5, min_hit_rate=0.0)
        self.assertGreaterEqual(ev["n_samples"], 5)
        self.assertIn("direction_hit_rate", ev)

    def test_ols_signal_backtest_strategy(self):
        out = run_ols_signal_backtest(_ohlcv(100), fee_bps=5)
        self.assertEqual(out["strategy"], "ols_walk_forward")
        self.assertIn("direction_hit_rate", out["metrics"])
        self.assertIn("evidence", out)

    def test_service_ols_strategy(self):
        out = BacktestService().run(_ohlcv(90), engine="pandas", strategy="ols_signal")
        self.assertEqual(out["strategy"], "ols_walk_forward")

    def test_ml_predict_includes_oos(self):
        result = MLEnsembleService().predict(_ohlcv(130), models=["sklearn"])
        self.assertIn("oos", result)
        self.assertEqual(result["confidence_kind"], "in_sample_max_proba")
        self.assertIn("evidence_ok", result)

    def test_ml_ridge_walk_forward(self):
        oos = evaluate_ml_ridge_walk_forward(_ohlcv(130), min_train=50, max_points=20)
        self.assertGreater(oos.get("n_samples", 0), 5)
        self.assertIn("direction_hit_rate", oos["metrics"])


class TestTradingGate(unittest.TestCase):
    def test_paper_ok(self):
        s = Settings(_env_file=None, trading_mode="paper", broker_name="paper")
        ok, reason = can_place(mode="paper", broker="paper", settings=s)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertEqual(live_venue(s), "paper")
        self.assertFalse(live_trading_allowed(s))

    def test_stub_blocked(self):
        s = Settings(_env_file=None, trading_mode="paper", broker_name="sbi")
        ok, reason = can_place(mode="paper", broker="sbi", settings=s)
        self.assertFalse(ok)
        self.assertIn("stub", reason)

    def test_live_requires_confirm(self):
        s = Settings(
            _env_file=None,
            trading_mode="live",
            broker_name="alpaca",
            alpaca_api_key="k",
            alpaca_api_secret="s",
            live_trading_confirm="",
        )
        ok, reason = can_place(mode="live", broker="alpaca", settings=s)
        self.assertFalse(ok)
        self.assertIn("LIVE_TRADING_CONFIRM", reason)
        self.assertEqual(live_venue(s), "blocked")

    def test_live_alpaca_with_confirm(self):
        s = Settings(
            _env_file=None,
            trading_mode="live",
            broker_name="alpaca",
            alpaca_api_key="k",
            alpaca_api_secret="s",
            live_trading_confirm="I_UNDERSTAND_LIVE_RISK",
        )
        ok, reason = can_place(mode="live", broker="alpaca", settings=s)
        self.assertTrue(ok)
        self.assertEqual(live_venue(s), "alpaca")
        self.assertTrue(live_trading_allowed(s))


if __name__ == "__main__":
    unittest.main()
