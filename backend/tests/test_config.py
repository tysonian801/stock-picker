import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_demo_data() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            admin_password="prod-pass",
            session_secret_key="prod-session",
            csrf_secret_key="prod-csrf",
            allow_demo_data=True,
        )


def test_production_accepts_non_placeholder_secrets_without_demo_data() -> None:
    settings = Settings(
        app_env="production",
        admin_password="prod-pass",
        session_secret_key="prod-session",
        csrf_secret_key="prod-csrf",
        allow_demo_data=False,
    )

    assert settings.app_env == "production"
