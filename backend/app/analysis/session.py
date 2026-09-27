"""Tokyo session helpers so morning scans do not use an unfinished daily bar."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def drop_incomplete_tokyo_session(df: pd.DataFrame, *, now: datetime | None = None) -> pd.DataFrame:
    """Drop today's bar before 15:15 JST (TSE close + settle slack)."""
    if df is None or df.empty or "ts" not in df.columns:
        return df
    try:
        from zoneinfo import ZoneInfo

        jst = ZoneInfo("Asia/Tokyo")
    except Exception:  # noqa: BLE001
        return df
    current = now.astimezone(jst) if now is not None else datetime.now(jst)
    last = pd.Timestamp(df.iloc[-1]["ts"])
    if last.tzinfo is None:
        last = last.tz_localize("UTC")
    last_jst = last.tz_convert(jst)
    if last_jst.date() == current.date() and (current.hour, current.minute) < (15, 15):
        return df.iloc[:-1].copy()
    return df


def close_trend(df: pd.DataFrame, lookback: int = 20) -> str:
    if df is None or len(df) < lookback:
        return "unknown"
    last = float(df.iloc[-1]["close"])
    ma = float(df["close"].rolling(lookback).mean().iloc[-1])
    if last != last or ma != ma or ma <= 0:  # NaN
        return "unknown"
    return "uptrend" if last >= ma else "downtrend"


def momentum_return(df: pd.DataFrame, lookback: int = 20) -> float | None:
    if df is None or len(df) <= lookback:
        return None
    last = float(df.iloc[-1]["close"])
    prev = float(df.iloc[-1 - lookback]["close"])
    if prev <= 0:
        return None
    return last / prev - 1.0


def lot_size_for(ticker: str, jp_lot: int = 100) -> int:
    name = (ticker or "").upper()
    if name.endswith(".T") or name.endswith(".JP"):
        return max(1, int(jp_lot))
    return 1


def round_to_lot(qty: float, lot: int) -> float:
    if lot <= 1:
        return float(max(0.0, qty))
    return float(max(0, int(qty // lot)) * lot)
