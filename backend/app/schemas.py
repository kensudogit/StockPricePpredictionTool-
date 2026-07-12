from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    environment: str
    trading_mode: str
    providers: list[dict[str, Any]]


class IngestRequest(BaseModel):
    ticker: str = Field(..., examples=["7203.T"])
    timeframe: str = "1d"
    limit: int = 100


class PredictRequest(BaseModel):
    ticker: str
    horizon: str = "1d"


class PipelineRequest(BaseModel):
    ticker: str = Field(..., examples=["7203.T"])
    quantity: float = 100


class PipelineResponse(BaseModel):
    ticker: str
    status: Optional[str] = None
    stages: dict[str, Any] = {}
    error: Optional[str] = None


class SymbolOut(BaseModel):
    id: int
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    asset_type: str
    currency: str

    model_config = {"from_attributes": True}


class BarOut(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


class PredictionOut(BaseModel):
    id: int
    model_name: str
    horizon: str
    predicted_at: datetime
    predicted_price: Optional[float] = None
    direction: Optional[str] = None
    confidence: Optional[float] = None

    model_config = {"from_attributes": True}


class SignalOut(BaseModel):
    id: int
    signal_type: str
    strength: Optional[float] = None
    rationale: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    id: int
    side: str
    quantity: float
    status: str
    mode: str
    avg_fill_price: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PositionOut(BaseModel):
    id: int
    symbol_id: int
    ticker: Optional[str] = None
    quantity: float
    avg_cost: Optional[float] = None
    unrealized_pnl: float
    realized_pnl: float

    model_config = {"from_attributes": True}


class RiskEventOut(BaseModel):
    id: int
    event_type: str
    severity: str
    message: str
    created_at: datetime
    acknowledged: bool

    model_config = {"from_attributes": True}


class SnsPostOut(BaseModel):
    id: int
    platform: str
    content: str
    status: str
    related_symbol: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PortfolioOut(BaseModel):
    id: int
    ts: datetime
    equity: float
    cash: float
    exposure: float
    daily_pnl: float

    model_config = {"from_attributes": True}


class MacroOut(BaseModel):
    series_code: str
    ts: datetime
    value: float
    source: str
