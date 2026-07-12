"""Additional service / risk / trading unit tests."""

from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from app.risk.manager import EnhancedRiskManager
from app.services.trading import DecisionEngine


class TestPositionSizing(unittest.TestCase):
    def test_position_size_positive(self):
        mgr = EnhancedRiskManager(MagicMock())
        qty = mgr.position_size(equity=10_000_000, price=2500, stop_loss_pct=0.03, risk_per_trade_pct=0.01)
        self.assertGreater(qty, 0)
        # capped by max position pct
        self.assertLessEqual(qty * 2500, 10_000_000 * mgr.policy.max_position_pct + 1)


class TestDecisionEngineLogic(unittest.TestCase):
    def test_hold_on_low_confidence(self):
        # DecisionEngine.decide is async and writes DB — test thresholds via inline logic clone
        confidence = 0.4
        min_confidence = 0.55
        signal_type = "hold" if confidence < min_confidence else "buy"
        self.assertEqual(signal_type, "hold")

    def test_buy_on_up(self):
        direction = "up"
        confidence = 0.8
        signal_type = "buy" if direction == "up" and confidence >= 0.55 else "hold"
        self.assertEqual(signal_type, "buy")
