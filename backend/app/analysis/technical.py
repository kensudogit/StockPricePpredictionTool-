"""Technical indicators: trend / oscillators / volatility / volume."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    line = ema_fast - ema_slow
    sig = _ema(line, signal)
    hist = line - sig
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": hist})


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3) -> pd.DataFrame:
    lowest = low.rolling(k).min()
    highest = high.rolling(k).max()
    stoch_k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    stoch_d = stoch_k.rolling(d).mean()
    return pd.DataFrame({"stoch_k": stoch_k, "stoch_d": stoch_d})


def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    return (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(window).mean()
    std = close.rolling(window).std()
    return pd.DataFrame(
        {
            "bb_mid": mid,
            "bb_upper": mid + num_std * std,
            "bb_lower": mid - num_std * std,
            "bb_width": (2 * num_std * std) / mid.replace(0, np.nan),
        }
    )


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.DataFrame:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(high, low, close, 1)
    atr_n = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=close.index).rolling(period).mean() / atr_n.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=close.index).rolling(period).mean() / atr_n.replace(0, np.nan)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return pd.DataFrame({"adx": dx.rolling(period).mean(), "plus_di": plus_di, "minus_di": minus_di})


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    tp = (high + low + close) / 3
    cum_vol = volume.cumsum().replace(0, np.nan)
    return (tp * volume).cumsum() / cum_vol


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Expect columns: open, high, low, close, volume."""
    out = df.copy()
    close, high, low, volume = out["close"], out["high"], out["low"], out["volume"]

    out["sma_5"] = sma(close, 5)
    out["sma_20"] = sma(close, 20)
    out["sma_50"] = sma(close, 50)
    out["sma_200"] = sma(close, 200)
    out["ema_12"] = _ema(close, 12)
    out["ema_26"] = _ema(close, 26)
    out = out.join(macd(close))
    out = out.join(adx(high, low, close))
    out["rsi_14"] = rsi(close, 14)
    out = out.join(stochastic(high, low, close))
    out["cci_20"] = cci(high, low, close)
    out["atr_14"] = atr(high, low, close)
    out = out.join(bollinger(close))
    out["vwap"] = vwap(high, low, close, volume)
    out["obv"] = obv(close, volume)

    # Trend label: price vs SMA20/SMA50
    out["trend"] = np.where(
        (close > out["sma_20"]) & (out["sma_20"] > out["sma_50"]),
        "uptrend",
        np.where((close < out["sma_20"]) & (out["sma_20"] < out["sma_50"]), "downtrend", "sideways"),
    )
    return out


def latest_snapshot(df: pd.DataFrame) -> dict:
    tech = compute_all(df)
    row = tech.dropna(subset=["sma_20", "rsi_14"]).iloc[-1]
    keys = [
        "sma_5", "sma_20", "sma_50", "sma_200", "ema_12", "ema_26",
        "macd", "macd_signal", "macd_hist", "adx", "plus_di", "minus_di",
        "rsi_14", "stoch_k", "stoch_d", "cci_20", "atr_14",
        "bb_mid", "bb_upper", "bb_lower", "bb_width", "vwap", "obv",
    ]
    snap = {k: (None if pd.isna(row.get(k)) else float(row[k])) for k in keys}
    snap["trend"] = str(row["trend"])
    snap["close"] = float(row["close"])
    return snap


def series_for_chart(df: pd.DataFrame, limit: int = 120) -> list[dict]:
    tech = compute_all(df).tail(limit)
    records = []
    for _, r in tech.iterrows():
        records.append(
            {
                "ts": r["ts"].isoformat() if hasattr(r["ts"], "isoformat") else str(r.get("ts", "")),
                "close": float(r["close"]),
                "sma_20": None if pd.isna(r.get("sma_20")) else float(r["sma_20"]),
                "ema_12": None if pd.isna(r.get("ema_12")) else float(r["ema_12"]),
                "rsi_14": None if pd.isna(r.get("rsi_14")) else float(r["rsi_14"]),
                "macd": None if pd.isna(r.get("macd")) else float(r["macd"]),
                "bb_upper": None if pd.isna(r.get("bb_upper")) else float(r["bb_upper"]),
                "bb_lower": None if pd.isna(r.get("bb_lower")) else float(r["bb_lower"]),
                "volume": float(r.get("volume") or 0),
            }
        )
    return records
