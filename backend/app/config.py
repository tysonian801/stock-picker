from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", env_ignore_empty=True)

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Stock Picker"
    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"
    timezone: str = "America/Denver"

    admin_email: str = "admin@example.com"
    admin_password: SecretStr = Field(default=SecretStr("change-me-in-local-env"))
    session_secret_key: SecretStr = Field(default=SecretStr("change-me-in-local-env"))
    csrf_secret_key: SecretStr = Field(default=SecretStr("change-me-in-local-env"))

    database_url: str = "sqlite:///./local-data/stock_picker.db"
    redis_url: str = "redis://localhost:6379/0"

    fmp_api_key: SecretStr | None = None
    alpha_vantage_api_key: SecretStr | None = None
    finnhub_api_key: SecretStr | None = None
    discord_webhook_url: str | None = None

    min_market_cap: int = 2_000_000_000
    min_price: float = 5.0
    min_avg_dollar_volume: int = 25_000_000
    strong_buy_min_opportunity: int = 80
    strong_buy_min_confidence: int = 75
    allow_demo_data: bool = True

    @model_validator(mode="after")
    def reject_placeholder_production_secrets(self) -> "Settings":
        if self.app_env != "production":
            return self
        placeholders = {
            self.admin_password.get_secret_value(),
            self.session_secret_key.get_secret_value(),
            self.csrf_secret_key.get_secret_value(),
        }
        if any(value.startswith("change-me") for value in placeholders):
            raise ValueError("production secrets must be provided through the environment")
        if self.allow_demo_data:
            raise ValueError("demo data must be disabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
