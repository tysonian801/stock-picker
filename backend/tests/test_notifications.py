import asyncio

import httpx
import pytest

from app.config import get_settings
from app.models import Notification, utc_now
from app.notifications import dispatch_queued_discord_notifications, sanitize_discord_text


def test_sanitize_discord_text_redacts_mentions() -> None:
    message = sanitize_discord_text("@everyone buy signal <@123456789012345678>")

    assert "@everyone" not in message
    assert "<@123456789012345678>" not in message
    assert "@redacted" in message


def test_discord_dispatch_failure_does_not_expose_webhook(monkeypatch, db) -> None:
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def post(self, url, json):
            request = httpx.Request("POST", url)
            response = httpx.Response(403, request=request)
            return response

    monkeypatch.setenv(
        "DISCORD_WEBHOOK_URL",
        "https://example.test/webhook/test-token",
    )
    get_settings.cache_clear()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: Client())
    db.add(
        Notification(
            channel="discord",
            status="queued",
            subject="subject",
            body="body",
            created_at=utc_now(),
        )
    )
    db.commit()

    try:
        sent = asyncio.run(dispatch_queued_discord_notifications(db))
    except RuntimeError as exc:
        pytest.fail(f"Webhook URL was exposed through an exception: {exc}")

    notification = db.query(Notification).one()
    assert sent == 0
    assert notification.status == "failed"
    get_settings.cache_clear()
