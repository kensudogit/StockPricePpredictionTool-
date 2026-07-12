"""Tests for ML / DL / RAG / backtest / risk / brokers"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.backtest.engine import BacktestService, run_pandas_backtest
from app.brokers.base import BrokerOrderRequest, PaperBroker, get_broker
from app.dl.models import DeepLearningService, _numpy_fallback
from app.llm.clients import NewsLLMService
from app.ml.ensemble import MLEnsembleService
from app.rag.store import embed_text
from app.risk.manager import RiskPolicy


class TestMLEnsemble(unittest.TestCase):
    def test_predict_with_enough_data(self,):
        # use fixture-like data
        import numpy as np

        n = 120
        rng = np.random.default_rng(0)
        close = 100 + np.cumsum(rng.normal(0, 1, n))
        df = pd.DataFrame(
            {
                "ts": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": rng.integers(1000, 5000, n).astype(float),
            }
        )
        result = MLEnsembleService().predict(df, models=["sklearn"])
        self.assertIn("consensus_signal", result)
        self.assertIn("upside_rate", result)
        self.assertIn("downside_rate", result)

    def test_insufficient_data(self):
        df = pd.DataFrame(
            {
                "ts": pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC"),
                "open": [1] * 10,
                "high": [1] * 10,
                "low": [1] * 10,
                "close": [1] * 10,
                "volume": [1] * 10,
            }
        )
        result = MLEnsembleService().predict(df)
        self.assertIn("error", result)


class TestDeepLearning(unittest.TestCase):
    def test_numpy_fallback(self):
        import numpy as np

        close = np.linspace(100, 110, 50)
        out = _numpy_fallback(close)
        self.assertIn("predicted_return", out)
        self.assertIn("direction", out)

    def test_service_unknown_model(self):
        df = pd.DataFrame({"close": [1, 2, 3]})
        out = DeepLearningService().predict(df, model="nope")
        self.assertIn("error", out)


class TestRagEmbed(unittest.TestCase):
    def test_embed_dim(self):
        v = embed_text("決算 増益 IR ニュース")
        self.assertEqual(len(v), 384)
        # roughly unit length
        import math

        norm = math.sqrt(sum(x * x for x in v))
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_empty_text(self):
        v = embed_text("")
        self.assertEqual(len(v), 384)
        self.assertEqual(sum(abs(x) for x in v), 0)


class TestBacktest(unittest.TestCase):
    def test_pandas_engine(self):
        import numpy as np

        n = 100
        close = 100 + np.cumsum(np.random.default_rng(1).normal(0, 1, n))
        df = pd.DataFrame(
            {
                "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": [1000] * n,
            }
        )
        result = run_pandas_backtest(df)
        self.assertEqual(result["engine"], "pandas")
        self.assertIn("total_return", result["metrics"])
        self.assertTrue(len(result["equity_curve"]) > 0)

    def test_service_dispatch(self):
        import numpy as np

        n = 80
        close = np.linspace(100, 120, n)
        df = pd.DataFrame(
            {
                "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": [1] * n,
            }
        )
        out = BacktestService().run(df, engine="pandas")
        self.assertEqual(out["engine"], "pandas")


class TestRiskPolicy(unittest.TestCase):
    def test_defaults(self):
        p = RiskPolicy()
        self.assertGreater(p.max_position_pct, 0)
        self.assertGreater(p.default_stop_loss_pct, 0)
        self.assertGreaterEqual(p.max_open_positions, 1)


class TestBrokers(unittest.TestCase):
    def test_paper_broker(self):
        broker = PaperBroker()

        async def _run():
            self.assertTrue(await broker.health())
            res = await broker.place_order(
                BrokerOrderRequest(ticker="7203.T", side="buy", quantity=10)
            )
            self.assertEqual(res.status, "filled")
            self.assertEqual(res.broker, "paper")

        import asyncio

        asyncio.run(_run())

    def test_get_broker_default(self):
        b = get_broker("paper")
        self.assertEqual(b.name, "paper")


class TestNewsLLMService(unittest.TestCase):
    def test_draft_modes_heuristic(self):
        svc = NewsLLMService(provider="heuristic")

        async def _run():
            s = await svc.summarize("テストニュース本文")
            self.assertTrue(len(s) > 0)
            sent = await svc.sentiment("増益 上昇")
            self.assertIn("label", sent)

        import asyncio

        asyncio.run(_run())
