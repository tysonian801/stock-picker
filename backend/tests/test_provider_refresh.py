import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.models import FundamentalSnapshot, PricePoint, SentimentSnapshot, Stock
from app.providers import (
    FmpProvider,
    FundamentalProviderRecord,
    PriceProviderRecord,
    ProviderRefresh,
    ProviderUnavailableError,
    SentimentProviderRecord,
)
from app.services import apply_provider_refresh


def test_apply_provider_refresh_persists_source_backed_records(db) -> None:
    timestamp = datetime(2026, 6, 24, tzinfo=UTC)
    refresh = ProviderRefresh(
        prices=[
            PriceProviderRecord(
                ticker="MSFT",
                close=420.0,
                source="test-provider",
                provider_timestamp=timestamp,
                observed_at=timestamp,
            )
        ],
        fundamentals=[
            FundamentalProviderRecord(
                ticker="MSFT",
                revenue_growth=0.12,
                gross_margin=0.68,
                operating_margin=0.41,
                debt_to_equity=0.3,
                pe_ratio=31.0,
                industry_pe=36.0,
                source="test-provider",
                provider_timestamp=timestamp,
                observed_at=timestamp,
            )
        ],
        sentiments=[
            SentimentProviderRecord(
                ticker="MSFT",
                sentiment_score=0.4,
                article_count=8,
                source="test-provider",
                provider_timestamp=timestamp,
                observed_at=timestamp,
            )
        ],
    )

    applied = apply_provider_refresh(db, refresh)
    stock = db.scalar(select(Stock).where(Stock.ticker == "MSFT"))
    assert stock is not None

    assert applied == 3
    assert db.scalar(
        select(PricePoint).where(
            PricePoint.stock_id == stock.id, PricePoint.source == "test-provider"
        )
    )
    assert db.scalar(
        select(FundamentalSnapshot).where(
            FundamentalSnapshot.stock_id == stock.id,
            FundamentalSnapshot.source == "test-provider",
        )
    )
    assert db.scalar(
        select(SentimentSnapshot).where(
            SentimentSnapshot.stock_id == stock.id,
            SentimentSnapshot.source == "test-provider",
        )
    )


def test_provider_http_errors_do_not_expose_api_keys(monkeypatch) -> None:
    class Response:
        status_code = 429

        def raise_for_status(self) -> None:
            raise http_status_error

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def get(self, *args, **kwargs):
            return Response()

    import httpx

    request = httpx.Request("GET", "https://example.test/quote?apikey=test-key")
    response = httpx.Response(429, request=request)
    http_status_error = httpx.HTTPStatusError("boom", request=request, response=response)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: Client())

    provider = FmpProvider(api_key=SecretStr("test-key"))

    with pytest.raises(ProviderUnavailableError) as exc:
        asyncio.run(provider.refresh(["MSFT"]))

    assert "test-key" not in str(exc.value)
    assert "apikey" not in str(exc.value)
