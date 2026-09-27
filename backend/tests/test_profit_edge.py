"""Profit gate: only trade when after-fee OOS EV is positive."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.config import Settings
from app.risk.manager import EnhancedRiskManager
from app.trading.edge import assess_edge


def _settings(**over):
    return Settings(_env_file=None, **over)


def _good_evidence() -> dict:
    return {
        "ok": True,
        "direction_hit_rate": 0.58,
        "n_samples": 40,
        "oos_strategy_return": 0.08,
        "oos_sharpe": 0.9,
        "expected_value": 0.002,
        "block_reason": None,
    }


class TestAssessEdge(unittest.TestCase):
    def test_hold_when_oos_return_not_positive(self):
        ev = _good_evidence()
        ev["oos_strategy_return"] = -0.02
        plan = assess_edge(
            evidence=ev,
            direction="up",
            last_close=100,
            predicted_price=102,
            trend="uptrend",
            rsi=50,
            settings=_settings(),
        )
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["action"], "hold")

    def test_hold_counter_trend(self):
        plan = assess_edge(
            evidence=_good_evidence(),
            direction="up",
            last_close=100,
            predicted_price=102,
            trend="downtrend",
            rsi=50,
            settings=_settings(),
        )
        self.assertEqual(plan["action"], "hold")
        self.assertIn("counter-trend", plan["block_reason"] or "")

    def test_hold_when_move_smaller_than_cost(self):
        plan = assess_edge(
            evidence=_good_evidence(),
            direction="up",
            last_close=100,
            predicted_price=100.02,
            trend="uptrend",
            rsi=50,
            settings=_settings(paper_fee_bps=5, min_expected_value=0.0008),
        )
        self.assertEqual(plan["action"], "hold")

    def test_buy_when_edge_and_trend_align(self):
        risk = EnhancedRiskManager(MagicMock())
        plan = assess_edge(
            evidence=_good_evidence(),
            direction="up",
            last_close=2500,
            predicted_price=2580,
            trend="uptrend",
            rsi=48,
            equity=10_000_000,
            settings=_settings(),
            risk=risk,
        )
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["action"], "buy")
        self.assertGreater(plan["suggested_qty"], 0)

    def test_hold_overbought_rsi(self):
        plan = assess_edge(
            evidence=_good_evidence(),
            direction="up",
            last_close=100,
            predicted_price=103,
            trend="uptrend",
            rsi=82,
            settings=_settings(),
        )
        self.assertEqual(plan["action"], "hold")


if __name__ == "__main__":
    unittest.main()
