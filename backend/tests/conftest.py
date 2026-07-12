"""Shared fixtures for StockAI backend tests."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    n = 120
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 1.5, n)
    low = close - rng.uniform(0.1, 1.5, n)
    open_ = close + rng.normal(0, 0.3, n)
    volume = rng.integers(1000, 5000, n).astype(float)
    ts = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


@pytest.fixture
def sample_bar_row():
    return {
        "ts": datetime(2024, 6, 1, tzinfo=timezone.utc),
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 10000.0,
        "source": "test",
    }
