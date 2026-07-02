from datetime import datetime

from pydantic import BaseModel, Field

from app.models import DataFreshness, Horizon, Signal, TradeSide


class LoginRequest(BaseModel):
    email: str
    password: str


class SessionResponse(BaseModel):
    email: str
    csrf_token: str


class StockResponse(BaseModel):
    id: int
    ticker: str
    name: str
    sector: str
    industry: str
    exchange: str
    market_cap: int
    avg_dollar_volume: int

    model_config = {"from_attributes": True}


class EvidenceResponse(BaseModel):
    id: int
    kind: str
    source: str
    source_url: str | None
    observed_at: datetime
    provider_timestamp: datetime
    summary: str

    model_config = {"from_attributes": True}


class RecommendationResponse(BaseModel):
    id: int
    stock: StockResponse
    latest_price: float | None
    horizon: Horizon
    signal: Signal
    opportunity_score: int
    confidence_score: int
    data_freshness: DataFreshness
    thesis: str
    risk_summary: str
    as_of: datetime
    evidence: list[EvidenceResponse] = []

    model_config = {"from_attributes": True}


class ScanRunResponse(BaseModel):
    id: int
    started_at: datetime
    completed_at: datetime | None
    status: str
    universe_count: int
    recommendations_count: int
    notes: str | None

    model_config = {"from_attributes": True}


class MockTradeCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    side: TradeSide
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    executed_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)


class MockTradeResponse(BaseModel):
    id: int
    ticker: str
    side: TradeSide
    quantity: float
    price: float
    executed_at: datetime
    note: str | None


class HoldingResponse(BaseModel):
    ticker: str
    name: str
    sector: str
    quantity: float
    cost_basis: float
    latest_price: float
    market_value: float
    unrealized_return_pct: float


class PortfolioResponse(BaseModel):
    total_cost_basis: float
    total_market_value: float
    total_return_pct: float
    holdings: list[HoldingResponse]
    benchmarks: dict[str, float]


class PerformancePoint(BaseModel):
    as_of: datetime
    close: float


class TradeMarker(BaseModel):
    side: TradeSide
    quantity: float
    price: float
    executed_at: datetime


class StockPerformanceResponse(BaseModel):
    ticker: str
    name: str
    points: list[PerformancePoint]
    markers: list[TradeMarker]


class NotificationResponse(BaseModel):
    id: int
    channel: str
    status: str
    subject: str
    body: str
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
