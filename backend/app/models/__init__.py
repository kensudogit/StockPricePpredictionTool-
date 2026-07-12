from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    exchange: Mapped[Optional[str]] = mapped_column(String(64))
    asset_type: Mapped[str] = mapped_column(String(32), default="equity")
    currency: Mapped[str] = mapped_column(String(8), default="JPY")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketBar(Base):
    __tablename__ = "market_bars"
    __table_args__ = (UniqueConstraint("symbol_id", "timeframe", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    volume: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4), default=0)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class MacroSeries(Base):
    __tablename__ = "macro_series"
    __table_args__ = (UniqueConstraint("series_code", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    series_code: Mapped[str] = mapped_column(String(64), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class MarginShort(Base):
    __tablename__ = "margin_short"
    __table_args__ = (UniqueConstraint("symbol_id", "as_of_date", "source"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    margin_buy: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 2))
    margin_sell: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 2))
    short_interest: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 2))
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon: Mapped[str] = mapped_column(String(16), nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    target_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    predicted_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    direction: Mapped[Optional[str]] = mapped_column(String(8))
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class TradingSignal(Base):
    __tablename__ = "trading_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    strength: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    prediction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("predictions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(16), default="pending")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    signal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trading_signals.id"))
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), default="market")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    limit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(String(16), default="new")
    mode: Mapped[str] = mapped_column(String(8), default="paper")
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(128))
    filled_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    avg_fill_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), unique=True, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    avg_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    take_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    leverage: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    exposure: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    daily_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class SnsPost(Base):
    __tablename__ = "sns_posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), default="x")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    related_symbol: Mapped[Optional[str]] = mapped_column(String(32))
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    external_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol_id: Mapped[Optional[int]] = mapped_column(ForeignKey("symbols.id"))
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="news")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    sentiment: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    sentiment_label: Mapped[Optional[str]] = mapped_column(String(16))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Fundamental(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (UniqueConstraint("symbol_id", "as_of_date", "source"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    per: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    pbr: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    roe: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    roa: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    eps: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    bps: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    operating_margin: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    equity_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 2))
    source: Mapped[str] = mapped_column(String(32), default="yahoo")
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class TechnicalSnapshot(Base):
    __tablename__ = "technical_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), default="1d")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    indicators: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol_id: Mapped[Optional[int]] = mapped_column(ForeignKey("symbols.id"))
    title: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(255))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    equity_curve: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RiskOrder(Base):
    __tablename__ = "risk_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    position_id: Mapped[Optional[int]] = mapped_column(ForeignKey("positions.id"))
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    order_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
