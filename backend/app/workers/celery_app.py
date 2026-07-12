from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

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
            "args": (["7203.T", "6758.T"],),
        },
    },
)

if __name__ == "__main__":
    celery_app.start()
