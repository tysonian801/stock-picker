from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.models import (
    DataFreshness,
    FundamentalSnapshot,
    Horizon,
    PricePoint,
    SentimentSnapshot,
    Signal,
    Stock,
)


@dataclass(frozen=True)
class ScoreInput:
    stock: Stock
    latest_price: PricePoint | None
    prior_price: PricePoint | None
    fundamentals: FundamentalSnapshot | None
    sentiment: SentimentSnapshot | None
    as_of: datetime


@dataclass(frozen=True)
class ScoreResult:
    horizon: Horizon
    signal: Signal
    opportunity_score: int
    confidence_score: int
    data_freshness: DataFreshness
    thesis: str
    risk_summary: str
    evidence_summaries: list[tuple[str, str, datetime, datetime, str]]


def _freshness(score_input: ScoreInput) -> DataFreshness:
    if not get_settings().allow_demo_data:
        sources = [
            getattr(score_input.latest_price, "source", ""),
            getattr(score_input.fundamentals, "source", ""),
            getattr(score_input.sentiment, "source", ""),
        ]
        if any(source.startswith("seeded-") for source in sources):
            return DataFreshness.MISSING
    required = [score_input.latest_price, score_input.fundamentals, score_input.sentiment]
    if any(item is None for item in required):
        return DataFreshness.MISSING
    assert score_input.latest_price and score_input.fundamentals and score_input.sentiment
    if _as_utc(score_input.latest_price.provider_timestamp) < score_input.as_of - timedelta(days=3):
        return DataFreshness.STALE
    if _as_utc(score_input.fundamentals.provider_timestamp) < score_input.as_of - timedelta(
        days=120
    ):
        return DataFreshness.STALE
    if _as_utc(score_input.sentiment.provider_timestamp) < score_input.as_of - timedelta(days=7):
        return DataFreshness.STALE
    if (
        score_input.sentiment.sentiment_score < -0.45
        and score_input.fundamentals.revenue_growth > 0.25
    ):
        return DataFreshness.CONTRADICTORY
    return DataFreshness.FRESH


def _clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def score_stock(score_input: ScoreInput) -> list[ScoreResult]:
    freshness = _freshness(score_input)
    if freshness != DataFreshness.FRESH:
        return [
            ScoreResult(
                horizon=Horizon.MID_TERM,
                signal=Signal.INSUFFICIENT_EVIDENCE,
                opportunity_score=0,
                confidence_score=0,
                data_freshness=freshness,
                thesis=(
                    "Recommendation suppressed because required market, fundamentals, "
                    "or sentiment data is not fresh and consistent."
                ),
                risk_summary=(
                    "No buy signal is emitted until the app has current, source-backed data."
                ),
                evidence_summaries=[],
            )
        ]

    assert score_input.latest_price and score_input.prior_price
    assert score_input.fundamentals and score_input.sentiment
    fundamentals = score_input.fundamentals
    sentiment = score_input.sentiment
    momentum = (
        score_input.latest_price.close - score_input.prior_price.close
    ) / score_input.prior_price.close
    valuation_discount = (
        fundamentals.industry_pe - fundamentals.pe_ratio
    ) / fundamentals.industry_pe

    quality = (
        fundamentals.revenue_growth * 110
        + fundamentals.gross_margin * 45
        + fundamentals.operating_margin * 70
        - fundamentals.debt_to_equity * 8
    )
    valuation = valuation_discount * 100
    sentiment_component = sentiment.sentiment_score * 45
    mid_term = _clamp_score(50 + momentum * 130 + sentiment_component + valuation * 0.25)
    long_term = _clamp_score(45 + quality * 0.5 + valuation * 0.35 + sentiment_component * 0.3)

    confidence = _clamp_score(
        55
        + min(sentiment.article_count, 20)
        + (10 if score_input.stock.avg_dollar_volume >= 50_000_000 else 0)
        + (10 if abs(momentum) <= 0.25 else -5)
    )

    return [
        _build_result(
            Horizon.MID_TERM, mid_term, confidence, score_input, momentum, valuation_discount
        ),
        _build_result(
            Horizon.LONG_TERM, long_term, confidence, score_input, momentum, valuation_discount
        ),
    ]


def _signal(opportunity: int, confidence: int) -> Signal:
    settings = get_settings()
    if (
        opportunity >= settings.strong_buy_min_opportunity
        and confidence >= settings.strong_buy_min_confidence
    ):
        return Signal.STRONG_BUY
    if opportunity >= 65 and confidence >= 60:
        return Signal.WATCH
    return Signal.HOLD


def _build_result(
    horizon: Horizon,
    opportunity: int,
    confidence: int,
    score_input: ScoreInput,
    momentum: float,
    valuation_discount: float,
) -> ScoreResult:
    assert score_input.latest_price and score_input.fundamentals and score_input.sentiment
    stock = score_input.stock
    fundamentals = score_input.fundamentals
    sentiment = score_input.sentiment
    signal = _signal(opportunity, confidence)
    thesis = (
        f"{stock.ticker} is a {horizon.value.replace('_', '-')} {signal.value.replace('_', ' ')} "
        f"signal as of {score_input.as_of.date()} with revenue growth of "
        f"{fundamentals.revenue_growth:.1%}, operating margin of "
        f"{fundamentals.operating_margin:.1%}, "
        f"and a P/E of {fundamentals.pe_ratio:.1f} versus the industry benchmark of "
        f"{fundamentals.industry_pe:.1f}. Recent price momentum is {momentum:.1%}, and sourced "
        f"sentiment is {sentiment.sentiment_score:.2f} across {sentiment.article_count} items."
    )
    risk = (
        "Primary risks: valuation gap may close slowly, sentiment can change quickly, "
        f"and debt-to-equity is {fundamentals.debt_to_equity:.2f}. "
        "This is a research signal, not personalized financial advice."
    )
    evidence = [
        (
            "price",
            score_input.latest_price.source,
            score_input.latest_price.observed_at,
            score_input.latest_price.provider_timestamp,
            f"Latest sourced close was {score_input.latest_price.close:.2f}.",
        ),
        (
            "fundamentals",
            fundamentals.source,
            fundamentals.observed_at,
            fundamentals.provider_timestamp,
            f"Revenue growth {fundamentals.revenue_growth:.1%}; "
            f"P/E {fundamentals.pe_ratio:.1f}; "
            f"industry P/E {fundamentals.industry_pe:.1f}.",
        ),
        (
            "sentiment",
            sentiment.source,
            sentiment.observed_at,
            sentiment.provider_timestamp,
            f"Sentiment score {sentiment.sentiment_score:.2f} from "
            f"{sentiment.article_count} sourced items.",
        ),
    ]
    return ScoreResult(
        horizon=horizon,
        signal=signal,
        opportunity_score=opportunity,
        confidence_score=confidence,
        data_freshness=DataFreshness.FRESH,
        thesis=thesis,
        risk_summary=risk,
        evidence_summaries=evidence,
    )


def current_utc() -> datetime:
    return datetime.now(UTC)
