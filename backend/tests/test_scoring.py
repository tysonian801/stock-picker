from datetime import timedelta

from sqlalchemy import select

from app.models import DataFreshness, SentimentSnapshot, Signal, Stock, utc_now
from app.scoring import ScoreInput, score_stock
from app.services import latest_price, prior_price


def test_scoring_emits_source_backed_strong_or_watch_signal(db) -> None:
    stock = db.scalar(select(Stock).where(Stock.ticker == "MSFT"))
    assert stock is not None

    results = score_stock(
        ScoreInput(
            stock=stock,
            latest_price=latest_price(db, stock.id),
            prior_price=prior_price(db, stock.id),
            fundamentals=stock.fundamentals[0],
            sentiment=db.scalar(
                select(SentimentSnapshot).where(SentimentSnapshot.stock_id == stock.id)
            ),
            as_of=utc_now(),
        )
    )

    assert len(results) == 2
    assert all(result.data_freshness == DataFreshness.FRESH for result in results)
    assert any(result.signal in {Signal.STRONG_BUY, Signal.WATCH} for result in results)
    assert all(result.evidence_summaries for result in results)


def test_scoring_suppresses_stale_fundamentals(db) -> None:
    stock = db.scalar(select(Stock).where(Stock.ticker == "MSFT"))
    assert stock is not None
    fundamentals = stock.fundamentals[0]
    fundamentals.provider_timestamp = utc_now() - timedelta(days=180)
    db.add(fundamentals)
    db.commit()

    result = score_stock(
        ScoreInput(
            stock=stock,
            latest_price=latest_price(db, stock.id),
            prior_price=prior_price(db, stock.id),
            fundamentals=fundamentals,
            sentiment=None,
            as_of=utc_now(),
        )
    )[0]

    assert result.signal == Signal.INSUFFICIENT_EVIDENCE
    assert result.opportunity_score == 0
    assert result.data_freshness in {DataFreshness.MISSING, DataFreshness.STALE}
