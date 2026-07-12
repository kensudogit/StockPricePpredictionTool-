"""Tests for app.analysis.technical"""

from __future__ import annotations

import unittest

import pandas as pd

from app.analysis.technical import (
    adx,
    atr,
    bollinger,
    cci,
    compute_all,
    latest_snapshot,
    macd,
    obv,
    rsi,
    series_for_chart,
    sma,
    stochastic,
    vwap,
)


class TestTechnicalIndicators(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np

        n = 80
        rng = np.random.default_rng(7)
        close = 100 + np.cumsum(rng.normal(0, 1.2, n))
        high = close + rng.uniform(0.2, 1.5, n)
        low = close - rng.uniform(0.2, 1.5, n)
        volume = rng.integers(1000, 8000, n).astype(float)
        cls.df = pd.DataFrame(
            {
                "ts": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
                "open": close + rng.normal(0, 0.2, n),
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )

    def test_sma_length(self):
        s = sma(self.df["close"], 5)
        self.assertEqual(len(s), len(self.df))
        self.assertFalse(pd.isna(s.iloc[-1]))

    def test_rsi_bounds(self):
        r = rsi(self.df["close"])
        val = float(r.dropna().iloc[-1])
        self.assertGreaterEqual(val, 0)
        self.assertLessEqual(val, 100)

    def test_macd_columns(self):
        m = macd(self.df["close"])
        self.assertTrue({"macd", "macd_signal", "macd_hist"}.issubset(m.columns))

    def test_stochastic_cci_atr_bb(self):
        st = stochastic(self.df["high"], self.df["low"], self.df["close"])
        self.assertIn("stoch_k", st.columns)
        self.assertFalse(cci(self.df["high"], self.df["low"], self.df["close"]).dropna().empty)
        self.assertFalse(atr(self.df["high"], self.df["low"], self.df["close"]).dropna().empty)
        bb = bollinger(self.df["close"])
        self.assertIn("bb_upper", bb.columns)

    def test_adx_vwap_obv(self):
        a = adx(self.df["high"], self.df["low"], self.df["close"])
        self.assertIn("adx", a.columns)
        self.assertFalse(vwap(self.df["high"], self.df["low"], self.df["close"], self.df["volume"]).dropna().empty)
        self.assertEqual(len(obv(self.df["close"], self.df["volume"])), len(self.df))

    def test_compute_all_and_snapshot(self):
        tech = compute_all(self.df)
        self.assertIn("rsi_14", tech.columns)
        snap = latest_snapshot(self.df)
        self.assertIn("trend", snap)
        self.assertIn("rsi_14", snap)
        series = series_for_chart(self.df, limit=20)
        self.assertEqual(len(series), 20)
