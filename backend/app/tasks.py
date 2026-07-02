from celery import Celery
from celery.schedules import crontab

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import Stock
from app.notifications import dispatch_queued_discord_notifications
from app.providers import (
    AlphaVantageProvider,
    FinnhubProvider,
    FmpProvider,
    FreeFirstProviderRegistry,
)
from app.seed import seed_reference_data
from app.services import apply_provider_refresh, run_scan

settings = get_settings()
celery_app = Celery("stock_picker", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.timezone = settings.timezone
celery_app.conf.beat_schedule = {
    "scan-pre-market": {"task": "app.tasks.scan_market", "schedule": crontab(hour=7, minute=30)},
    "scan-mid-day": {"task": "app.tasks.scan_market", "schedule": crontab(hour=11, minute=30)},
    "scan-near-close": {"task": "app.tasks.scan_market", "schedule": crontab(hour=13, minute=45)},
    "scan-after-close": {"task": "app.tasks.scan_market", "schedule": crontab(hour=15, minute=30)},
}


@celery_app.task(name="app.tasks.scan_market")
def scan_market() -> int:
    init_db()
    with SessionLocal() as db:
        seed_reference_data(db)
        tickers = [
            row[0] for row in db.query(Stock.ticker).filter(Stock.sector != "Benchmark").all()
        ]
        registry = FreeFirstProviderRegistry(
            providers=[
                FmpProvider(settings.fmp_api_key),
                AlphaVantageProvider(settings.alpha_vantage_api_key),
                FinnhubProvider(settings.finnhub_api_key),
            ]
        )
        import asyncio

        applied = apply_provider_refresh(db, asyncio.run(registry.refresh_all(tickers)))
        scan = run_scan(db)
        if applied == 0 and not settings.allow_demo_data:
            scan.notes = (
                "No provider records were refreshed; recommendations rely on existing stored data."
            )
            db.commit()
        asyncio.run(dispatch_queued_discord_notifications(db))
        return scan.id
