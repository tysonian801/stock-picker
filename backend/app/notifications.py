import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Notification, Recommendation, utc_now
from app.services import record_notification

MENTION_PATTERN = re.compile(r"@(?:everyone|here|[!&]?\d+)")


def sanitize_discord_text(text: str) -> str:
    return MENTION_PATTERN.sub("@redacted", text)[:1800]


def build_recommendation_message(recommendation: Recommendation) -> tuple[str, str]:
    subject = (
        f"{recommendation.stock.ticker} {recommendation.horizon.value} "
        f"{recommendation.signal.value}: {recommendation.opportunity_score}/100"
    )
    body = sanitize_discord_text(
        f"{subject}\n"
        f"Confidence: {recommendation.confidence_score}/100\n"
        f"As of: {recommendation.as_of.isoformat()}\n"
        f"{recommendation.thesis}\n\n"
        f"{recommendation.risk_summary}"
    )
    return subject, body


async def _post_discord_message(client: httpx.AsyncClient, webhook_url: str, body: str) -> None:
    try:
        response = await client.post(webhook_url, json={"content": body})
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Discord webhook returned HTTP {exc.response.status_code}") from None
    except httpx.HTTPError:
        raise RuntimeError("Discord webhook request failed") from None


async def send_discord_notification(db: Session, recommendation: Recommendation) -> None:
    settings = get_settings()
    subject, body = build_recommendation_message(recommendation)
    if not settings.discord_webhook_url:
        record_notification(
            db, subject, body, status="skipped", recommendation_id=recommendation.id
        )
        return
    async with httpx.AsyncClient(timeout=10) as client:
        await _post_discord_message(client, str(settings.discord_webhook_url), body)
    record_notification(db, subject, body, status="sent", recommendation_id=recommendation.id)


async def dispatch_queued_discord_notifications(db: Session) -> int:
    settings = get_settings()
    queued = db.scalars(
        select(Notification)
        .where(Notification.channel == "discord", Notification.status == "queued")
        .order_by(Notification.created_at)
        .limit(10)
    ).all()
    if not queued:
        return 0
    if not settings.discord_webhook_url:
        for notification in queued:
            notification.status = "skipped"
        db.commit()
        return len(queued)
    sent = 0
    async with httpx.AsyncClient(timeout=10) as client:
        for notification in queued:
            body = sanitize_discord_text(notification.body)
            try:
                await _post_discord_message(client, str(settings.discord_webhook_url), body)
            except RuntimeError:
                notification.status = "failed"
            else:
                notification.status = "sent"
                notification.sent_at = utc_now()
                sent += 1
    db.commit()
    return sent
