from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import FundamentalSnapshot, PricePoint, SentimentSnapshot, Stock

SAMPLE_STOCKS = [
    (
        "MSFT",
        "Microsoft Corporation",
        "Technology",
        "Software",
        "NASDAQ",
        3_100_000_000_000,
        9_000_000_000,
        418.0,
        0.16,
        0.69,
        0.44,
        0.36,
        34.0,
        38.0,
        0.54,
    ),
    (
        "LLY",
        "Eli Lilly and Company",
        "Healthcare",
        "Drug Manufacturers",
        "NYSE",
        810_000_000_000,
        3_200_000_000,
        870.0,
        0.28,
        0.79,
        0.39,
        1.55,
        58.0,
        46.0,
        0.42,
    ),
    (
        "COST",
        "Costco Wholesale Corporation",
        "Consumer Defensive",
        "Discount Stores",
        "NASDAQ",
        390_000_000_000,
        1_900_000_000,
        882.0,
        0.08,
        0.13,
        0.04,
        0.31,
        52.0,
        31.0,
        0.32,
    ),
    (
        "XOM",
        "Exxon Mobil Corporation",
        "Energy",
        "Oil and Gas Integrated",
        "NYSE",
        520_000_000_000,
        2_400_000_000,
        116.0,
        0.06,
        0.28,
        0.18,
        0.20,
        14.0,
        13.0,
        0.18,
    ),
    (
        "AVGO",
        "Broadcom Inc.",
        "Technology",
        "Semiconductors",
        "NASDAQ",
        720_000_000_000,
        4_000_000_000,
        1580.0,
        0.23,
        0.74,
        0.46,
        1.64,
        33.0,
        39.0,
        0.48,
    ),
    (
        "CAT",
        "Caterpillar Inc.",
        "Industrials",
        "Farm and Heavy Construction Machinery",
        "NYSE",
        175_000_000_000,
        1_100_000_000,
        350.0,
        0.11,
        0.35,
        0.21,
        1.80,
        17.0,
        21.0,
        0.26,
    ),
]

BENCHMARKS = [
    (
        "SPY",
        "SPDR S&P 500 ETF Trust",
        "Benchmark",
        "S&P 500 ETF",
        "NYSEARCA",
        500_000_000_000,
        30_000_000_000,
        550.0,
    ),
    (
        "QQQ",
        "Invesco QQQ Trust",
        "Benchmark",
        "Nasdaq 100 ETF",
        "NASDAQ",
        280_000_000_000,
        15_000_000_000,
        475.0,
    ),
    (
        "VTI",
        "Vanguard Total Stock Market ETF",
        "Benchmark",
        "Total Market ETF",
        "NYSEARCA",
        420_000_000_000,
        4_000_000_000,
        270.0,
    ),
]


def seed_reference_data(db: Session) -> None:
    if not get_settings().allow_demo_data:
        return
    now = datetime.now(UTC)
    for row in SAMPLE_STOCKS:
        (
            ticker,
            name,
            sector,
            industry,
            exchange,
            market_cap,
            volume,
            price,
            revenue_growth,
            gross_margin,
            operating_margin,
            debt_to_equity,
            pe_ratio,
            industry_pe,
            sentiment,
        ) = row
        stock = _ensure_stock(db, ticker, name, sector, industry, exchange, market_cap, volume)
        _ensure_prices(db, stock, now, price)
        if not db.scalar(
            select(FundamentalSnapshot).where(FundamentalSnapshot.stock_id == stock.id)
        ):
            db.add(
                FundamentalSnapshot(
                    stock_id=stock.id,
                    as_of=now,
                    revenue_growth=revenue_growth,
                    gross_margin=gross_margin,
                    operating_margin=operating_margin,
                    debt_to_equity=debt_to_equity,
                    pe_ratio=pe_ratio,
                    industry_pe=industry_pe,
                    source="seeded-provider-snapshot",
                    provider_timestamp=now,
                )
            )
        if not db.scalar(select(SentimentSnapshot).where(SentimentSnapshot.stock_id == stock.id)):
            db.add(
                SentimentSnapshot(
                    stock_id=stock.id,
                    as_of=now,
                    sentiment_score=sentiment,
                    article_count=12,
                    source="seeded-sentiment-snapshot",
                    provider_timestamp=now,
                )
            )
    for ticker, name, sector, industry, exchange, market_cap, volume, price in BENCHMARKS:
        stock = _ensure_stock(db, ticker, name, sector, industry, exchange, market_cap, volume)
        _ensure_prices(db, stock, now, price)
    db.commit()


def _ensure_stock(
    db: Session,
    ticker: str,
    name: str,
    sector: str,
    industry: str,
    exchange: str,
    market_cap: int,
    volume: int,
) -> Stock:
    stock = db.scalar(select(Stock).where(Stock.ticker == ticker))
    if stock:
        return stock
    stock = Stock(
        ticker=ticker,
        name=name,
        sector=sector,
        industry=industry,
        exchange=exchange,
        market_cap=market_cap,
        avg_dollar_volume=volume,
    )
    db.add(stock)
    db.flush()
    return stock


def _ensure_prices(db: Session, stock: Stock, now: datetime, latest_price: float) -> None:
    existing = db.scalar(select(PricePoint).where(PricePoint.stock_id == stock.id))
    if existing:
        return
    for days_ago, multiplier in [(120, 0.86), (60, 0.92), (30, 0.96), (0, 1.0)]:
        as_of = now - timedelta(days=days_ago)
        db.add(
            PricePoint(
                stock_id=stock.id,
                as_of=as_of,
                close=round(latest_price * multiplier, 2),
                source="seeded-market-snapshot",
                provider_timestamp=as_of,
            )
        )
