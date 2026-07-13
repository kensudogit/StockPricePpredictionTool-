"""Unit tests for explainability helpers (no DB)."""

from __future__ import annotations

import unittest

import numpy as np

from app.analysis.explain import explain_linear_attribution, narrative_from_explanation


class TestExplainLinear(unittest.TestCase):
    def test_attribution_sorted(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(80, 4))
        y = X @ np.array([0.5, -0.2, 0.1, 0.0]) + 10
        x_last = X[-1]
        pred = 10.2
        out = explain_linear_attribution(
            feature_names=["a", "b", "c", "d"],
            X_train=X[:-1],
            y_train=y[:-1],
            x_last=x_last,
            predicted_value=pred,
        )
        self.assertEqual(out["method"], "linear_shap")
        self.assertEqual(len(out["features"]), 4)
        impacts = [abs(f["impact"]) for f in out["features"]]
        self.assertEqual(impacts, sorted(impacts, reverse=True))

    def test_narrative(self):
        expl = {
            "method": "linear_shap",
            "note": "test",
            "top_positive": [{"label": "A", "impact": 0.1}],
            "top_negative": [{"label": "B", "impact": -0.05}],
        }
        lines = narrative_from_explanation(expl, signal="buy", confidence=0.66)
        self.assertTrue(any("BUY" in x or "buy" in x.lower() or "シグナル" in x for x in lines))


if __name__ == "__main__":
    unittest.main()
