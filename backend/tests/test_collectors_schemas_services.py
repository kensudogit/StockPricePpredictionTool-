"""Tests for collectors, schemas, services (pure), prediction helpers"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.collectors.base import Bar, MarketDataProvider
from app.collectors.commercial import BloombergProvider, JpxDataProvider, QuickProvider
from app.collectors.registry import MACRO_SERIES, get_primary_provider, get_providers
from app.schemas import HealthResponse, IngestRequest, PipelineRequest
from app.services.prediction import _build_features, _ols_predict, _dir_confidence
from app.services.sns import SnsService
import numpy as np
import pandas as pd


class TestCollectorsRegistry(unittest.TestCase):
    def test_macro_series_keys(self):
        for key in ("NIKKEI", "VIX", "USDJPY", "SP500"):
            self.assertIn(key, MACRO_SERIES)

    def test_providers_include_yahoo(self):
        providers = get_providers()
        names = [p.name for p in providers]
        self.assertIn("yahoo", names)
        self.assertIn("stooq", names)
        self.assertEqual(names[0], "yahoo")

    def test_primary_provider(self):
        p = get_primary_provider()
        self.assertIsInstance(p, MarketDataProvider)


class TestCommercialStubs(unittest.TestCase):
    def test_jpx_health_false(self):
        import asyncio

        self.assertFalse(asyncio.run(JpxDataProvider().health()))

    def test_quick_bloomberg_empty_bars(self):
        import asyncio

        async def _run():
            self.assertEqual(await QuickProvider().fetch_bars("7203.T"), [])
            self.assertEqual(await BloombergProvider().fetch_bars("AAPL"), [])

        asyncio.run(_run())


class TestSchemas(unittest.TestCase):
    def test_ingest_request(self):
        body = IngestRequest(ticker="7203.T")
        self.assertEqual(body.timeframe, "1d")

    def test_pipeline_request(self):
        body = PipelineRequest(ticker="7203.T", quantity=50)
        self.assertEqual(body.quantity, 50)

    def test_health_response(self):
        h = HealthResponse(
            status="ok",
            environment="test",
            trading_mode="paper",
            providers=[{"name": "yahoo", "available": True}],
        )
        self.assertEqual(h.status, "ok")


class TestPredictionHelpers(unittest.TestCase):
    def test_build_features(self):
        n = 60
        df = pd.DataFrame(
            {
                "close": np.linspace(100, 120, n),
                "high": np.linspace(101, 121, n),
                "low": np.linspace(99, 119, n),
                "volume": np.full(n, 1000.0),
            }
        )
        feat = _build_features(df)
        self.assertIn("return_1", feat.columns)
        self.assertGreater(len(feat), 0)

    def test_ols_and_dir(self):
        X = np.random.default_rng(0).normal(size=(40, 3))
        y = X @ np.array([0.5, -0.2, 0.1]) + 0.01
        pred = _ols_predict(X, y, X[-1])
        self.assertIsInstance(pred, float)
        direction, conf = _dir_confidence(X, (y > 0).astype(int), X[-1])
        self.assertIn(direction, {"up", "down"})
        self.assertGreaterEqual(conf, 0)
        self.assertLessEqual(conf, 1)


class TestSnsService(unittest.TestCase):
    def test_draft_market_comment(self):
        svc = SnsService(db=MagicMock())
        text = svc.draft_market_comment("7203.T", "up", 0.8, 2500.0)
        self.assertIn("7203.T", text)
        self.assertIn("上昇", text)
