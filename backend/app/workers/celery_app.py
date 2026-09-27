"""Celery beat/app. Optional: API boots without celery installed."""

from app.config import get_settings

settings = get_settings()

try:
    from celery import Celery
    from celery.schedules import crontab
except ImportError:  # slim local / Railway API-only image
    Celery = None
    crontab = None


class _DummyCelery:
    """Stand-in so task modules import when Celery is not installed."""

    def task(self, *args, **kwargs):
        def deco(fn):
            return fn

        return deco

    def start(self):
        raise RuntimeError("celery is not installed")


if Celery is not None:
    celery_app = Celery(
        "stockai",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["app.workers.tasks"],
    )
    celery_app.conf.update(
        timezone="Asia/Tokyo",
        enable_utc=True,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        beat_schedule={
            "ingest-macro-hourly": {
                "task": "app.workers.tasks.ingest_macro_task",
                "schedule": crontab(minute=5),
            },
            "pipeline-watchlist-daily": {
                "task": "app.workers.tasks.run_watchlist_pipeline",
                "schedule": crontab(hour=9, minute=15),
            },
            "daily-ops-after-close": {
                "task": "app.workers.tasks.daily_ops_task",
                "schedule": crontab(hour=16, minute=20),
            },
        },
    )
else:
    celery_app = _DummyCelery()

if __name__ == "__main__":
    celery_app.start()
