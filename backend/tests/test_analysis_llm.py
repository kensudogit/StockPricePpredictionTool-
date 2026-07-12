"""Tests for app.analysis.fundamental / news / llm"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.analysis.fundamental import _safe_float, fetch_fundamentals_yahoo
from app.llm.clients import LLMClient, heuristic_sentiment
from app.analysis.news import RSS_FEEDS


class TestFundamentalHelpers(unittest.TestCase):
    def test_safe_float_ok(self):
        self.assertEqual(_safe_float("1.5"), 1.5)

    def test_safe_float_none(self):
        self.assertIsNone(_safe_float(None))
        self.assertIsNone(_safe_float("x"))

    @patch("app.analysis.fundamental.yf.Ticker")
    def test_fetch_fundamentals_yahoo(self, mock_ticker):
        mock_ticker.return_value.info = {
            "trailingPE": 12.0,
            "priceToBook": 1.2,
            "returnOnEquity": 0.1,
            "returnOnAssets": 0.05,
            "trailingEps": 100.0,
            "bookValue": 50.0,
            "operatingMargins": 0.15,
            "debtToEquity": 50.0,
            "marketCap": 1e12,
            "sector": "Auto",
        }
        data = fetch_fundamentals_yahoo("7203.T")
        self.assertEqual(data["per"], 12.0)
        self.assertEqual(data["source"], "yahoo")
        self.assertIsNotNone(data["equity_ratio"])


class TestNewsRegistry(unittest.TestCase):
    def test_rss_feeds_configured(self):
        self.assertIn("reuters", RSS_FEEDS)
        self.assertIn("earnings", RSS_FEEDS)
        for cfg in RSS_FEEDS.values():
            self.assertIn("url", cfg)
            self.assertIn("category", cfg)


class TestLLMHeuristic(unittest.TestCase):
    def test_positive_sentiment(self):
        r = heuristic_sentiment("増益で上方修正、上昇基調")
        self.assertEqual(r["label"], "positive")
        self.assertGreater(r["score"], 0)

    def test_negative_sentiment(self):
        r = heuristic_sentiment("減益で下方修正、下落")
        self.assertEqual(r["label"], "negative")

    def test_heuristic_provider_complete(self):
        client = LLMClient(provider="heuristic")
        import asyncio

        out = asyncio.run(client.complete("sys", "hello world test"))
        self.assertIn("hello", out)
