from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import (
    DataFreshness,
    Evidence,
    FundamentalSnapshot,
    Horizon,
    MockTrade,
    Notification,
    PricePoint,
    Recommendation,
    ScanRun,
    SentimentSnapshot,
    Signal,
    Stock,
    TradeSide,
    utc_now,
)
from app.providers import ProviderRefresh
from app.schemas import (
    EvidenceResponse,
    HoldingResponse,
    MockTradeCreate,
    MockTradeResponse,
    PerformancePoint,
    PortfolioResponse,
    RecommendationResponse,
    StockPerformanceResponse,
    StockResponse,
    TradeMarker,
)
from app.scoring import ScoreInput, score_stock


def latest_price(db: Session, stock_id: int) -> PricePoint | None:
    return db.scalar(
        select(PricePoint).where(PricePoint.stock_id == stock_id).order_by(desc(PricePoint.as_of))
    )


def prior_price(db: Session, stock_id: int) -> PricePoint | None:
    prices = db.scalars(
        select(PricePoint)
        .where(PricePoint.stock_id == stock_id)
        .order_by(desc(PricePoint.as_of))
        .limit(2)
    ).all()
    if len(prices) < 2:
        return None
    return prices[1]


def run_scan(db: Session) -> ScanRun:
    settings = get_settings()
    scan = ScanRun(status="running")
    db.add(scan)
    db.flush()
    stocks = db.scalars(
        select(Stock)
        .where(
            Stock.active.is_(True),
            Stock.sector != "Benchmark",
            Stock.market_cap >= settings.min_market_cap,
            Stock.avg_dollar_volume >= settings.min_avg_dollar_volume,
        )
        .order_by(Stock.sector, Stock.ticker)
    ).all()
    scan.universe_count = len(stocks)
    as_of = utc_now()
    created = 0
    for stock in stocks:
        latest = latest_price(db, stock.id)
        if latest and latest.close < settings.min_price:
            continue
        fundamentals = db.scalar(
            select(FundamentalSnapshot)
            .where(FundamentalSnapshot.stock_id == stock.id)
            .order_by(desc(FundamentalSnapshot.as_of))
        )
        sentiment = db.scalar(
            select(SentimentSnapshot)
            .where(SentimentSnapshot.stock_id == stock.id)
            .order_by(desc(SentimentSnapshot.as_of))
        )
        score_input = ScoreInput(
            stock=stock,
            latest_price=latest,
            prior_price=prior_price(db, stock.id),
            fundamentals=fundamentals,
            sentiment=sentiment,
            as_of=as_of,
        )
        for result in score_stock(score_input):
            recommendation = Recommendation(
                stock_id=stock.id,
                scan_run_id=scan.id,
                horizon=result.horizon,
                signal=result.signal,
                opportunity_score=result.opportunity_score,
                confidence_score=result.confidence_score,
                data_freshness=result.data_freshness,
                thesis=result.thesis,
                risk_summary=result.risk_summary,
                as_of=as_of,
            )
            db.add(recommendation)
            db.flush()
            for kind, source, observed_at, provider_timestamp, summary in result.evidence_summaries:
                db.add(
                    Evidence(
                        recommendation_id=recommendation.id,
                        kind=kind,
                        source=source,
                        observed_at=observed_at,
                        provider_timestamp=provider_timestamp,
                        summary=summary,
                    )
                )
            if result.signal == Signal.STRONG_BUY:
                db.add(
                    Notification(
                        recommendation_id=recommendation.id,
                        channel="discord",
                        status="queued",
                        subject=f"{stock.ticker} {result.horizon.value} strong buy signal",
                        body=f"{result.thesis}\n\n{result.risk_summary}",
                    )
                )
            created += 1
    scan.status = "completed"
    scan.completed_at = utc_now()
    scan.recommendations_count = created
    db.commit()
    _create_sell_risk_recommendations(db, scan, as_of)
    db.commit()
    return scan


def apply_provider_refresh(db: Session, refresh: ProviderRefresh) -> int:
    applied = 0
    for record in refresh.prices:
        stock = db.scalar(select(Stock).where(Stock.ticker == record.ticker))
        if not stock:
            continue
        existing = db.scalar(
            select(PricePoint).where(
                PricePoint.stock_id == stock.id,
                PricePoint.as_of == record.provider_timestamp,
            )
        )
        if existing:
            existing.close = record.close
            existing.source = record.source
            existing.provider_timestamp = record.provider_timestamp
            existing.observed_at = record.observed_at
            applied += 1
            continue
        db.add(
            PricePoint(
                stock_id=stock.id,
                as_of=record.provider_timestamp,
                close=record.close,
                source=record.source,
                provider_timestamp=record.provider_timestamp,
                observed_at=record.observed_at,
            )
        )
        applied += 1
    for record in refresh.fundamentals:
        stock = db.scalar(select(Stock).where(Stock.ticker == record.ticker))
        if not stock:
            continue
        db.add(
            FundamentalSnapshot(
                stock_id=stock.id,
                as_of=record.provider_timestamp,
                revenue_growth=record.revenue_growth,
                gross_margin=record.gross_margin,
                operating_margin=record.operating_margin,
                debt_to_equity=record.debt_to_equity,
                pe_ratio=record.pe_ratio,
                industry_pe=record.industry_pe,
                source=record.source,
                provider_timestamp=record.provider_timestamp,
                observed_at=record.observed_at,
            )
        )
        applied += 1
    for record in refresh.sentiments:
        stock = db.scalar(select(Stock).where(Stock.ticker == record.ticker))
        if not stock:
            continue
        db.add(
            SentimentSnapshot(
                stock_id=stock.id,
                as_of=record.provider_timestamp,
                sentiment_score=record.sentiment_score,
                article_count=record.article_count,
                source=record.source,
                provider_timestamp=record.provider_timestamp,
                observed_at=record.observed_at,
            )
        )
        applied += 1
    db.commit()
    return applied


def _create_sell_risk_recommendations(db: Session, scan: ScanRun, as_of) -> None:
    trade_rows = db.execute(
        select(MockTrade, Stock).join(Stock, Stock.id == MockTrade.stock_id)
    ).all()
    quantity_by_stock: dict[int, float] = defaultdict(float)
    cost_by_stock: dict[int, float] = defaultdict(float)
    stock_by_id: dict[int, Stock] = {}
    for trade, stock in trade_rows:
        stock_by_id[stock.id] = stock
        signed_quantity = trade.quantity if trade.side == TradeSide.BUY else -trade.quantity
        quantity_by_stock[stock.id] += signed_quantity
        cost_by_stock[stock.id] += signed_quantity * trade.price
    for stock_id, quantity in quantity_by_stock.items():
        if quantity <= 0:
            continue
        price = latest_price(db, stock_id)
        if not price:
            continue
        average_cost = cost_by_stock[stock_id] / quantity
        drawdown = (price.close - average_cost) / average_cost
        if drawdown > -0.10:
            continue
        stock = stock_by_id[stock_id]
        recommendation = Recommendation(
            stock_id=stock.id,
            scan_run_id=scan.id,
            horizon=Horizon.MID_TERM,
            signal=Signal.SELL_RISK,
            opportunity_score=0,
            confidence_score=80,
            data_freshness=DataFreshness.FRESH,
            thesis=(
                f"{stock.ticker} has a sell-risk signal as of {as_of.date()} because the paper "
                f"position is down {drawdown:.1%} versus its tracked cost basis."
            ),
            risk_summary="This is a paper-trading risk alert, not an instruction to trade.",
            as_of=as_of,
        )
        db.add(recommendation)
        db.flush()
        db.add(
            Evidence(
                recommendation_id=recommendation.id,
                kind="position-risk",
                source=price.source,
                observed_at=price.observed_at,
                provider_timestamp=price.provider_timestamp,
                summary=f"Latest close {price.close:.2f}; tracked average cost {average_cost:.2f}.",
            )
        )
        db.add(
            Notification(
                recommendation_id=recommendation.id,
                channel="discord",
                status="queued",
                subject=f"{stock.ticker} sell-risk signal",
                body=f"{recommendation.thesis}\n\n{recommendation.risk_summary}",
            )
        )
        scan.recommendations_count += 1


def list_recommendations(db: Session, signal: Signal | None = None) -> list[RecommendationResponse]:
    latest_scan_id = db.scalar(
        select(ScanRun.id)
        .where(ScanRun.status == "completed")
        .order_by(desc(ScanRun.completed_at), desc(ScanRun.started_at))
        .limit(1)
    )
    if latest_scan_id is None:
        return []

    stmt = (
        select(Recommendation)
        .options(selectinload(Recommendation.stock), selectinload(Recommendation.evidence))
        .where(Recommendation.scan_run_id == latest_scan_id)
        .order_by(desc(Recommendation.as_of), desc(Recommendation.opportunity_score))
        .limit(100)
    )
    if signal:
        stmt = stmt.where(Recommendation.signal == signal)
    recommendations = db.scalars(stmt).all()
    return [
        _recommendation_response(item, latest_price(db, item.stock_id)) for item in recommendations
    ]


def _recommendation_response(
    recommendation: Recommendation, price: PricePoint | None
) -> RecommendationResponse:
    return RecommendationResponse(
        id=recommendation.id,
        stock=StockResponse.model_validate(recommendation.stock),
        latest_price=price.close if price else None,
        horizon=recommendation.horizon,
        signal=recommendation.signal,
        opportunity_score=recommendation.opportunity_score,
        confidence_score=recommendation.confidence_score,
        data_freshness=recommendation.data_freshness,
        thesis=recommendation.thesis,
        risk_summary=recommendation.risk_summary,
        as_of=recommendation.as_of,
        evidence=[
            EvidenceResponse.model_validate(evidence) for evidence in recommendation.evidence
        ],
    )


def create_mock_trade(db: Session, payload: MockTradeCreate) -> MockTrade:
    ticker = payload.ticker.upper()
    stock = db.scalar(select(Stock).where(Stock.ticker == ticker))
    if not stock:
        raise ValueError(f"Unknown ticker: {ticker}")
    price = payload.price
    if price is None:
        latest = latest_price(db, stock.id)
        if latest is None:
            raise ValueError(f"No trusted price available for {ticker}")
        price = latest.close
    trade = MockTrade(
        stock_id=stock.id,
        side=payload.side,
        quantity=payload.quantity,
        price=price,
        executed_at=payload.executed_at or datetime.now(UTC),
        note=payload.note,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def list_mock_trades(db: Session) -> list[MockTradeResponse]:
    rows = db.execute(select(MockTrade, Stock).join(Stock, Stock.id == MockTrade.stock_id)).all()
    return [
        MockTradeResponse(
            id=trade.id,
            ticker=stock.ticker,
            side=trade.side,
            quantity=trade.quantity,
            price=trade.price,
            executed_at=trade.executed_at,
            note=trade.note,
        )
        for trade, stock in rows
    ]


def portfolio_summary(db: Session) -> PortfolioResponse:
    rows = db.execute(select(MockTrade, Stock).join(Stock, Stock.id == MockTrade.stock_id)).all()
    quantities: dict[int, float] = defaultdict(float)
    costs: dict[int, float] = defaultdict(float)
    stocks: dict[int, Stock] = {}
    for trade, stock in rows:
        stocks[stock.id] = stock
        signed_quantity = trade.quantity if trade.side == TradeSide.BUY else -trade.quantity
        quantities[stock.id] += signed_quantity
        costs[stock.id] += signed_quantity * trade.price
    holdings: list[HoldingResponse] = []
    total_cost = 0.0
    total_value = 0.0
    for stock_id, quantity in quantities.items():
        if quantity <= 0:
            continue
        stock = stocks[stock_id]
        price = latest_price(db, stock_id)
        if not price:
            continue
        cost_basis = costs[stock_id]
        market_value = quantity * price.close
        total_cost += cost_basis
        total_value += market_value
        holdings.append(
            HoldingResponse(
                ticker=stock.ticker,
                name=stock.name,
                sector=stock.sector,
                quantity=round(quantity, 6),
                cost_basis=round(cost_basis, 2),
                latest_price=price.close,
                market_value=round(market_value, 2),
                unrealized_return_pct=round(((market_value - cost_basis) / cost_basis) * 100, 2)
                if cost_basis
                else 0.0,
            )
        )
    return PortfolioResponse(
        total_cost_basis=round(total_cost, 2),
        total_market_value=round(total_value, 2),
        total_return_pct=round(((total_value - total_cost) / total_cost) * 100, 2)
        if total_cost
        else 0.0,
        holdings=holdings,
        benchmarks=_benchmark_returns(db),
    )


def stock_performance(db: Session, ticker: str) -> StockPerformanceResponse:
    stock = db.scalar(select(Stock).where(Stock.ticker == ticker.upper()))
    if not stock:
        raise ValueError(f"Unknown ticker: {ticker.upper()}")
    prices = db.scalars(
        select(PricePoint).where(PricePoint.stock_id == stock.id).order_by(PricePoint.as_of)
    ).all()
    trades = db.scalars(
        select(MockTrade).where(MockTrade.stock_id == stock.id).order_by(MockTrade.executed_at)
    ).all()
    return StockPerformanceResponse(
        ticker=stock.ticker,
        name=stock.name,
        points=[PerformancePoint(as_of=point.as_of, close=point.close) for point in prices],
        markers=[
            TradeMarker(
                side=trade.side,
                quantity=trade.quantity,
                price=trade.price,
                executed_at=trade.executed_at,
            )
            for trade in trades
        ],
    )


def _benchmark_returns(db: Session) -> dict[str, float]:
    returns: dict[str, float] = {}
    for ticker in ["SPY", "QQQ", "VTI"]:
        stock = db.scalar(select(Stock).where(Stock.ticker == ticker))
        if not stock:
            continue
        prices = db.scalars(
            select(PricePoint).where(PricePoint.stock_id == stock.id).order_by(PricePoint.as_of)
        ).all()
        if len(prices) >= 2:
            returns[ticker] = round(
                ((prices[-1].close - prices[0].close) / prices[0].close) * 100, 2
            )
    return returns


def record_notification(
    db: Session,
    subject: str,
    body: str,
    status: str = "queued",
    recommendation_id: int | None = None,
) -> Notification:
    notification = Notification(
        recommendation_id=recommendation_id,
        channel="discord",
        status=status,
        subject=subject,
        body=body,
        sent_at=utc_now() if status == "sent" else None,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
