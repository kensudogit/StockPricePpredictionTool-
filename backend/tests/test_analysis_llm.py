"""Tests for app.analysis.fundamental / news / llm"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.analysis.fundamental import _safe_float, fetch_fundamentals_yahoo, parse_yahoo_jp_quote_html
from app.llm.clients import LLMClient, heuristic_sentiment
from app.analysis.news import RSS_FEEDS


class TestFundamentalHelpers(unittest.TestCase):
    def test_safe_float_ok(self):
        self.assertEqual(_safe_float("1.5"), 1.5)

    def test_safe_float_none(self):
        self.assertIsNone(_safe_float(None))
        self.assertIsNone(_safe_float("x"))

    @patch("app.analysis.fundamental.fetch_fundamentals_yahoo_jp")
    @patch("app.analysis.fundamental.yf.Ticker")
    def test_fetch_fundamentals_yahoo(self, mock_ticker, mock_jp):
        mock_jp.return_value = {
            "per": None,
            "pbr": None,
            "roe": None,
            "roa": None,
            "eps": None,
            "bps": None,
            "operating_margin": None,
            "equity_ratio": None,
            "market_cap": None,
            "source": "yahoo",
            "meta": {"note": "skip jp"},
        }
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

    @patch("app.analysis.fundamental.httpx.Client")
    def test_fetch_fundamentals_prefers_yahoo_jp(self, mock_client):
        html = (
            '<dt class="_DataListItem__term_x"><span>PER</span></dt>'
            '<dd><span>11.26</span></dd>'
            '<dt class="_DataListItem__term_x"><span>PBR</span></dt>'
            '<dd><span>0.95</span></dd>'
        )
        resp = MagicMock()
        resp.text = html
        resp.raise_for_status = MagicMock()
        mock_client.return_value.__enter__.return_value.get.return_value = resp
        data = fetch_fundamentals_yahoo("7203.T")
        self.assertEqual(data["per"], 11.26)
        self.assertEqual(data["pbr"], 0.95)
        self.assertEqual(data["source"], "yahoo.co.jp")

    def test_parse_yahoo_jp_quote_html(self):
        html = """
        <dt class="_DataListItem__term_x"><span>PER</span><span>（会社予想）</span></dt>
        <dd class="_DataListItem__description_x"><span>11.26</span></dd>
        <dt class="_DataListItem__term_x"><span>PBR</span><span>（実績）</span></dt>
        <dd class="_DataListItem__description_x"><span>0.95</span></dd>
        <dt class="_DataListItem__term_x"><span>ROE</span><span>（実績）</span></dt>
        <dd class="_DataListItem__description_x"><span>10.15</span></dd>
        <dt class="_DataListItem__term_x"><span>EPS</span><span>（会社予想）</span></dt>
        <dd class="_DataListItem__description_x"><span>265.55</span></dd>
        """
        parsed = parse_yahoo_jp_quote_html(html)
        self.assertEqual(parsed["per"], 11.26)
        self.assertEqual(parsed["pbr"], 0.95)
        self.assertAlmostEqual(parsed["roe"] or 0, 0.1015)
        self.assertEqual(parsed["eps"], 265.55)


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
