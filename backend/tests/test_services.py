from sqlalchemy import select

from app.models import Notification, Recommendation, Signal
from app.schemas import MockTradeCreate
from app.services import (
    create_mock_trade,
    list_recommendations,
    portfolio_summary,
    run_scan,
    stock_performance,
)


def test_run_scan_creates_recommendations_with_evidence(db) -> None:
    scan = run_scan(db)
    recommendations = db.scalars(select(Recommendation)).all()

    assert scan.status == "completed"
    assert scan.universe_count > 0
    assert len(recommendations) == scan.recommendations_count
    assert any(
        item.signal in {Signal.STRONG_BUY, Signal.WATCH, Signal.HOLD} for item in recommendations
    )
    assert any(item.evidence for item in recommendations)
    assert db.scalars(select(Notification).where(Notification.channel == "discord")).all()


def test_list_recommendations_includes_latest_price(db) -> None:
    run_scan(db)

    recommendations = list_recommendations(db)

    assert recommendations
    assert all(item.latest_price is not None for item in recommendations)


def test_list_recommendations_returns_only_latest_scan(db) -> None:
    first_scan = run_scan(db)
    second_scan = run_scan(db)

    recommendations = list_recommendations(db)

    assert recommendations
    assert second_scan.recommendations_count > 0
    assert len(recommendations) == second_scan.recommendations_count
    assert len(recommendations) != first_scan.recommendations_count * 2


def test_mock_trade_updates_portfolio_summary(db) -> None:
    create_mock_trade(db, MockTradeCreate(ticker="MSFT", side="buy", quantity=2, price=400))

    portfolio = portfolio_summary(db)

    assert portfolio.total_cost_basis == 800
    assert portfolio.total_market_value > 0
    assert portfolio.holdings[0].ticker == "MSFT"
    assert {"SPY", "QQQ", "VTI"}.issubset(portfolio.benchmarks)

    performance = stock_performance(db, "MSFT")
    assert performance.points
    assert performance.markers[0].side == "buy"


def test_scan_creates_sell_risk_for_underwater_position(db) -> None:
    create_mock_trade(db, MockTradeCreate(ticker="MSFT", side="buy", quantity=1, price=500))

    run_scan(db)

    sell_risk = db.scalars(
        select(Recommendation).where(Recommendation.signal == Signal.SELL_RISK)
    ).all()
    assert sell_risk
    assert db.scalars(select(Notification).where(Notification.subject.contains("sell-risk"))).all()
