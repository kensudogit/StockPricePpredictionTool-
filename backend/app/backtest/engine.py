"""Backtesting engines: vectorbt / backtrader / pandas fallback (Zipline adapter stub)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BacktestRun


def _sma_crossover_signals(close: pd.Series, fast: int = 10, slow: int = 30) -> pd.Series:
    f = close.rolling(fast).mean()
    s = close.rolling(slow).mean()
    sig = pd.Series(0, index=close.index)
    sig[f > s] = 1
    sig[f < s] = -1
    return sig.fillna(0)


def run_pandas_backtest(df: pd.DataFrame, fast: int = 10, slow: int = 30, fee_bps: float = 5) -> dict[str, Any]:
    close = df["close"].astype(float)
    signal = _sma_crossover_signals(close, fast, slow)
    position = signal.shift(1).fillna(0)
    rets = close.pct_change().fillna(0)
    strat_rets = position * rets - (position.diff().abs().fillna(0) * fee_bps / 10000.0)
    equity = (1 + strat_rets).cumprod()
    total_return = float(equity.iloc[-1] - 1)
    sharpe = float(strat_rets.mean() / (strat_rets.std() + 1e-12) * np.sqrt(252))
    max_dd = float((equity / equity.cummax() - 1).min())
    win_rate = float((strat_rets[strat_rets != 0] > 0).mean()) if (strat_rets != 0).any() else 0.0
    curve = [
        {"ts": str(df.iloc[i].get("ts", i)), "equity": float(equity.iloc[i])}
        for i in range(0, len(equity), max(1, len(equity) // 100))
    ]
    return {
        "engine": "pandas",
        "strategy": "sma_crossover",
        "metrics": {
            "total_return": total_return,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "trades": int(position.diff().abs().sum() / 2),
        },
        "equity_curve": curve,
        "params": {"fast": fast, "slow": slow, "fee_bps": fee_bps},
    }


def run_vectorbt_backtest(df: pd.DataFrame, fast: int = 10, slow: int = 30) -> dict[str, Any]:
    try:
        import vectorbt as vbt
    except ImportError:
        out = run_pandas_backtest(df, fast, slow)
        out["warning"] = "vectorbt not installed; used pandas engine"
        return out

    close = df["close"].astype(float)
    fast_ma = vbt.MA.run(close, window=fast)
    slow_ma = vbt.MA.run(close, window=slow)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)
    pf = vbt.Portfolio.from_signals(close, entries, exits, fees=0.0005, freq="1D")
    stats = pf.stats()
    equity = pf.value()
    curve = [
        {"ts": str(equity.index[i]), "equity": float(equity.iloc[i])}
        for i in range(0, len(equity), max(1, len(equity) // 100))
    ]
    return {
        "engine": "vectorbt",
        "strategy": "sma_crossover",
        "metrics": {
            "total_return": float(stats.get("Total Return [%]", 0) / 100.0),
            "sharpe": float(stats.get("Sharpe Ratio", 0) or 0),
            "max_drawdown": float(stats.get("Max Drawdown [%]", 0) or 0) / -100.0,
            "win_rate": float(stats.get("Win Rate [%]", 0) or 0) / 100.0,
        },
        "equity_curve": curve,
        "params": {"fast": fast, "slow": slow},
    }


def run_backtrader_backtest(df: pd.DataFrame, fast: int = 10, slow: int = 30) -> dict[str, Any]:
    try:
        import backtrader as bt
    except ImportError:
        out = run_pandas_backtest(df, fast, slow)
        out["warning"] = "backtrader not installed; used pandas engine"
        return out

    class SmaCross(bt.Strategy):
        params = dict(fast=fast, slow=slow)

        def __init__(self):
            self.sma_fast = bt.ind.SMA(period=self.p.fast)
            self.sma_slow = bt.ind.SMA(period=self.p.slow)
            self.crossover = bt.ind.CrossOver(self.sma_fast, self.sma_slow)

        def next(self):
            if not self.position and self.crossover > 0:
                self.buy()
            elif self.position and self.crossover < 0:
                self.close()

    data = df.copy()
    if "ts" in data.columns:
        data = data.set_index(pd.to_datetime(data["ts"]))
    data = data.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    feed = bt.feeds.PandasData(dataname=data)
    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmaCross)
    cerebro.adddata(feed)
    cerebro.broker.setcash(10_000_000)
    cerebro.broker.setcommission(commission=0.0005)
    start = cerebro.broker.getvalue()
    cerebro.run()
    end = cerebro.broker.getvalue()
    total_return = end / start - 1
    return {
        "engine": "backtrader",
        "strategy": "sma_crossover",
        "metrics": {
            "total_return": float(total_return),
            "sharpe": None,
            "max_drawdown": None,
            "win_rate": None,
            "final_value": float(end),
        },
        "equity_curve": [],
        "params": {"fast": fast, "slow": slow},
    }


def run_zipline_stub(df: pd.DataFrame, **kwargs) -> dict[str, Any]:
    out = run_pandas_backtest(df, **{k: v for k, v in kwargs.items() if k in {"fast", "slow"}})
    out["engine"] = "zipline_stub"
    out["warning"] = "Zipline is pinned to older stacks; use vectorbt/backtrader. Adapter stub delegates to pandas."
    return out


class BacktestService:
    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db

    def run(
        self,
        df: pd.DataFrame,
        engine: str = "vectorbt",
        fast: int = 10,
        slow: int = 30,
    ) -> dict[str, Any]:
        engine = engine.lower()
        if engine == "backtrader":
            return run_backtrader_backtest(df, fast, slow)
        if engine == "zipline":
            return run_zipline_stub(df, fast=fast, slow=slow)
        if engine == "pandas":
            return run_pandas_backtest(df, fast, slow)
        return run_vectorbt_backtest(df, fast, slow)

    async def run_and_store(
        self,
        ticker: str,
        df: pd.DataFrame,
        engine: str = "vectorbt",
        fast: int = 10,
        slow: int = 30,
    ) -> dict[str, Any]:
        result = self.run(df, engine=engine, fast=fast, slow=slow)
        if self.db is not None:
            rec = BacktestRun(
                ticker=ticker,
                strategy=result.get("strategy", "sma_crossover"),
                engine=result.get("engine", engine),
                params=result.get("params") or {},
                metrics=result.get("metrics") or {},
                equity_curve=result.get("equity_curve") or [],
                finished_at=datetime.now(timezone.utc),
            )
            self.db.add(rec)
            await self.db.commit()
            await self.db.refresh(rec)
            result["id"] = rec.id
        return result
