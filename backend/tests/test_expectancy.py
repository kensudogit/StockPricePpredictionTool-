"""Expectancy ranking, Kelly, and trailing stops (no network)."""

from __future__ import annotations

import unittest

from app.trading.expectancy import allocate_book, compute_trail, kelly_fraction, profit_score


def _plan(**over):
    base = {
        "ok": True,
        "action": "buy",
        "expected_value": 0.002,
        "oos_sharpe": 0.8,
        "predicted_return": 0.02,
        "suggested_qty": 400,
    }
    base.update(over)
    return base


class TestKellyAndScore(unittest.TestCase):
    def test_quarter_kelly_positive(self):
        # p=0.55, W=0.02, L=0.01 → b=2, f*=0.325, *0.25=0.08125 → cap 0.05
        k = kelly_fraction(0.55, 0.02, -0.01, fraction=0.25, cap=0.05)
        self.assertAlmostEqual(k, 0.05, places=6)

    def test_kelly_zero_when_edge_negative(self):
        self.assertEqual(kelly_fraction(0.40, 0.01, -0.01), 0.0)

    def test_score_zero_when_ev_not_positive(self):
        self.assertEqual(profit_score({"expected_value": -0.001, "oos_sharpe": 1, "predicted_return": 0.05}), 0.0)


class TestAllocateBook(unittest.TestCase):
    def test_ranks_higher_ev_first_and_caps_count(self):
        rows = [
            {"ticker": "AAA.T", "last_close": 1000, "plan": _plan(expected_value=0.001, oos_sharpe=0.3)},
            {"ticker": "BBB.T", "last_close": 1000, "plan": _plan(expected_value=0.004, oos_sharpe=1.2, predicted_return=0.03)},
            {"ticker": "CCC.T", "last_close": 1000, "plan": _plan(expected_value=0.002, oos_sharpe=0.5)},
        ]
        book = allocate_book(
            rows,
            equity=10_000_000,
            risk_per_trade_pct=0.01,
            max_new_trades=2,
            max_position_pct=0.10,
            stop_loss_pct=0.03,
        )
        self.assertEqual(len(book["picks"]), 2)
        self.assertEqual(book["picks"][0]["ticker"], "BBB.T")
        self.assertGreater(book["expected_portfolio_yen"], 0)
        self.assertGreater(book["picks"][0]["weight"], book["picks"][1]["weight"])

    def test_skips_already_open(self):
        rows = [{"ticker": "7203.T", "last_close": 2500, "plan": _plan()}]
        book = allocate_book(
            rows,
            equity=10_000_000,
            risk_per_trade_pct=0.01,
            max_new_trades=3,
            max_position_pct=0.10,
            stop_loss_pct=0.03,
            open_tickers={"7203.T"},
        )
        self.assertEqual(book["picks"], [])
        self.assertEqual(book["skipped_open"], ["7203.T"])


class TestTrail(unittest.TestCase):
    def test_long_locks_breakeven_at_one_r(self):
        stop, reason = compute_trail(
            quantity=100,
            avg_cost=100.0,
            last=103.5,
            stop=97.0,
            sl_pct=0.03,
            trail_pct=0.02,
            lock_r=1.0,
        )
        self.assertEqual(reason, "lock_breakeven")
        self.assertGreater(stop, 100.0)
        self.assertGreater(stop, 97.0)

    def test_long_trails_after_one_and_half_r(self):
        stop, reason = compute_trail(
            quantity=100,
            avg_cost=100.0,
            last=106.0,
            stop=97.0,
            sl_pct=0.03,
            trail_pct=0.02,
            lock_r=1.0,
        )
        self.assertEqual(reason, "trail")
        self.assertAlmostEqual(stop, 106.0 * 0.98, places=4)

    def test_short_locks_breakeven(self):
        stop, reason = compute_trail(
            quantity=-50,
            avg_cost=100.0,
            last=96.5,
            stop=103.0,
            sl_pct=0.03,
            trail_pct=0.02,
            lock_r=1.0,
        )
        self.assertEqual(reason, "lock_breakeven")
        self.assertLess(stop, 100.0)


if __name__ == "__main__":
    unittest.main()
