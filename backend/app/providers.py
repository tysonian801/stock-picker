from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr


@dataclass(frozen=True)
class PriceProviderRecord:
    ticker: str
    close: float
    source: str
    provider_timestamp: datetime
    observed_at: datetime


@dataclass(frozen=True)
class FundamentalProviderRecord:
    ticker: str
    revenue_growth: float
    gross_margin: float
    operating_margin: float
    debt_to_equity: float
    pe_ratio: float
    industry_pe: float
    source: str
    provider_timestamp: datetime
    observed_at: datetime


@dataclass(frozen=True)
class SentimentProviderRecord:
    ticker: str
    sentiment_score: float
    article_count: int
    source: str
    provider_timestamp: datetime
    observed_at: datetime


@dataclass(frozen=True)
class ProviderRefresh:
    prices: list[PriceProviderRecord]
    fundamentals: list[FundamentalProviderRecord]
    sentiments: list[SentimentProviderRecord]


class ProviderUnavailableError(RuntimeError):
    pass


class MarketDataProvider:
    name = "base"

    async def refresh(self, tickers: list[str]) -> ProviderRefresh:
        raise ProviderUnavailableError(f"{self.name} is not configured")


class FreeFirstProviderRegistry:
    def __init__(self, providers: list[MarketDataProvider]) -> None:
        self.providers = providers

    async def refresh_all(self, tickers: list[str]) -> ProviderRefresh:
        prices: list[PriceProviderRecord] = []
        fundamentals: list[FundamentalProviderRecord] = []
        sentiments: list[SentimentProviderRecord] = []
        for provider in self.providers:
            try:
                refresh = await provider.refresh(tickers)
            except ProviderUnavailableError:
                continue
            prices.extend(refresh.prices)
            fundamentals.extend(refresh.fundamentals)
            sentiments.extend(refresh.sentiments)
        return ProviderRefresh(prices=prices, fundamentals=fundamentals, sentiments=sentiments)


async def _get_json(
    client: httpx.AsyncClient,
    provider_name: str,
    url: str,
    params: dict[str, str],
) -> Any:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise ProviderUnavailableError(
            f"{provider_name} returned HTTP {exc.response.status_code}"
        ) from None
    except httpx.HTTPError:
        raise ProviderUnavailableError(f"{provider_name} request failed") from None


class FmpProvider(MarketDataProvider):
    name = "financial-modeling-prep"

    def __init__(self, api_key: SecretStr | None) -> None:
        self.api_key = api_key

    async def refresh(self, tickers: list[str]) -> ProviderRefresh:
        if not self.api_key:
            raise ProviderUnavailableError("FMP API key is not configured")
        now = datetime.now(UTC)
        joined = ",".join(tickers)
        async with httpx.AsyncClient(timeout=15) as client:
            quotes = await _get_json(
                client,
                self.name,
                f"https://financialmodelingprep.com/api/v3/quote/{joined}",
                {"apikey": self.api_key.get_secret_value()},
            )
            ratio_payloads: list[dict[str, Any]] = []
            for ticker in tickers:
                payload = await _get_json(
                    client,
                    self.name,
                    f"https://financialmodelingprep.com/api/v3/ratios-ttm/{ticker}",
                    {"apikey": self.api_key.get_secret_value()},
                )
                for item in payload:
                    if isinstance(item, dict):
                        ratio_payloads.append({"symbol": ticker, **item})
        price_records = [
            PriceProviderRecord(
                ticker=str(item["symbol"]).upper(),
                close=float(item["price"]),
                source=self.name,
                provider_timestamp=_timestamp(item.get("timestamp"), now),
                observed_at=now,
            )
            for item in quotes
            if isinstance(item, dict) and item.get("symbol") and _is_number(item.get("price"))
        ]
        industry_pe = _average_pe(ratio_payloads)
        fundamental_records = [
            FundamentalProviderRecord(
                ticker=str(item["symbol"]).upper(),
                revenue_growth=0.0,
                gross_margin=float(item.get("grossProfitMarginTTM") or 0),
                operating_margin=float(item.get("operatingProfitMarginTTM") or 0),
                debt_to_equity=float(item.get("debtEquityRatioTTM") or 0),
                pe_ratio=float(item.get("peRatioTTM") or 0),
                industry_pe=industry_pe,
                source=self.name,
                provider_timestamp=now,
                observed_at=now,
            )
            for item in ratio_payloads
            if isinstance(item, dict) and item.get("symbol")
        ]
        return ProviderRefresh(
            prices=price_records, fundamentals=fundamental_records, sentiments=[]
        )


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha-vantage"

    def __init__(self, api_key: SecretStr | None) -> None:
        self.api_key = api_key

    async def refresh(self, tickers: list[str]) -> ProviderRefresh:
        if not self.api_key:
            raise ProviderUnavailableError("Alpha Vantage API key is not configured")
        now = datetime.now(UTC)
        prices: list[PriceProviderRecord] = []
        async with httpx.AsyncClient(timeout=15) as client:
            for ticker in tickers:
                payload = await _get_json(
                    client,
                    self.name,
                    "https://www.alphavantage.co/query",
                    {
                        "function": "GLOBAL_QUOTE",
                        "symbol": ticker,
                        "apikey": self.api_key.get_secret_value(),
                    },
                )
                quote = payload.get("Global Quote", {})
                price = quote.get("05. price")
                if _is_number(price):
                    prices.append(
                        PriceProviderRecord(
                            ticker=ticker.upper(),
                            close=float(price),
                            source=self.name,
                            provider_timestamp=now,
                            observed_at=now,
                        )
                    )
        return ProviderRefresh(prices=prices, fundamentals=[], sentiments=[])


class FinnhubProvider(MarketDataProvider):
    name = "finnhub"

    def __init__(self, api_key: SecretStr | None) -> None:
        self.api_key = api_key

    async def refresh(self, tickers: list[str]) -> ProviderRefresh:
        if not self.api_key:
            raise ProviderUnavailableError("Finnhub API key is not configured")
        now = datetime.now(UTC)
        sentiments: list[SentimentProviderRecord] = []
        async with httpx.AsyncClient(timeout=15) as client:
            for ticker in tickers:
                payload = await _get_json(
                    client,
                    self.name,
                    "https://finnhub.io/api/v1/news-sentiment",
                    {"symbol": ticker, "token": self.api_key.get_secret_value()},
                )
                score = payload.get("sentiment", {}).get("bullishPercent")
                article_count = payload.get("buzz", {}).get("articlesInLastWeek")
                if _is_number(score) and _is_number(article_count):
                    sentiments.append(
                        SentimentProviderRecord(
                            ticker=ticker.upper(),
                            sentiment_score=(float(score) * 2) - 1,
                            article_count=int(float(article_count)),
                            source=self.name,
                            provider_timestamp=now,
                            observed_at=now,
                        )
                    )
        return ProviderRefresh(prices=[], fundamentals=[], sentiments=sentiments)


def _timestamp(value: Any, fallback: datetime) -> datetime:
    if _is_number(value):
        return datetime.fromtimestamp(float(value), UTC)
    return fallback


def _is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _average_pe(items: Any) -> float:
    ratios = [
        float(item["peRatioTTM"])
        for item in items
        if isinstance(item, dict)
        and _is_number(item.get("peRatioTTM"))
        and float(item["peRatioTTM"]) > 0
    ]
    return sum(ratios) / len(ratios) if ratios else 1.0
