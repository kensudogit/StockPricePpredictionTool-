"""Daily ops helpers (no network)."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock

from app.config import Settings
from app.risk.manager import EnhancedRiskManager
from app.services.ops import flatten_side, parse_watchlist


class TestOpsHelpers(unittest.TestCase):
    def test_flatten_side(self):
        self.assertEqual(flatten_side(100), "sell")
        self.assertEqual(flatten_side(-50), "buy")

    def test_parse_watchlist_from_settings(self):
        s = Settings(_env_file=None, watchlist="7203.T, 6758.T")
        self.assertEqual(s.watchlist_tickers, ["7203.T", "6758.T"])
        self.assertEqual(parse_watchlist("8306.T,6501.T"), ["8306.T", "6501.T"])

    def test_daily_auto_execute_default_off(self):
        s = Settings(_env_file=None)
        self.assertFalse(s.daily_auto_execute)

    def test_flatten_skips_size_and_daily_loss_limits(self):
        rm = EnhancedRiskManager(MagicMock())
        ok, reason = asyncio.run(
            rm.check_order(
                equity=1_000_000,
                order_notional=9_000_000,
                daily_pnl=-80_000,
                opening_new=False,
            )
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")


if __name__ == "__main__":
    unittest.main()
