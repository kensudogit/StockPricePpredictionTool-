"""Import smoke tests for all app packages / modules."""

from __future__ import annotations

import importlib
import unittest

MODULES = [
    "app",
    "app.main",
    "app.config",
    "app.schemas",
    "app.db",
    "app.db.bootstrap",
    "app.models",
    "app.api",
    "app.api.routes",
    "app.api.tests_routes",
    "app.api.analysis_routes",
    "app.agents",
    "app.agents.pipeline",
    "app.analysis",
    "app.analysis.technical",
    "app.analysis.fundamental",
    "app.analysis.news",
    "app.collectors",
    "app.collectors.base",
    "app.collectors.yahoo",
    "app.collectors.alphavantage",
    "app.collectors.polygon",
    "app.collectors.finnhub",
    "app.collectors.twelve_data",
    "app.collectors.commercial",
    "app.collectors.registry",
    "app.services",
    "app.services.ingestion",
    "app.services.prediction",
    "app.services.trading",
    "app.services.sns",
    "app.services.margin",
    "app.services.market_data",
    "app.llm",
    "app.llm.clients",
    "app.ml",
    "app.ml.ensemble",
    "app.dl",
    "app.dl.models",
    "app.rag",
    "app.rag.store",
    "app.brokers",
    "app.brokers.base",
    "app.backtest",
    "app.backtest.engine",
    "app.risk",
    "app.risk.manager",
    "app.workers",
    "app.workers.celery_app",
    "app.workers.tasks",
]


class TestAllModuleImports(unittest.TestCase):
    def test_import_each_module(self):
        errors = []
        for name in MODULES:
            try:
                importlib.import_module(name)
            except Exception as e:  # noqa: BLE001 — collect all failures
                errors.append(f"{name}: {e}")
        self.assertEqual(errors, [], msg="\n".join(errors))
