from app.tasks import celery_app


def test_four_daily_scan_schedules_are_configured() -> None:
    assert set(celery_app.conf.beat_schedule) == {
        "scan-pre-market",
        "scan-mid-day",
        "scan-near-close",
        "scan-after-close",
    }
