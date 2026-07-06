import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379/0"))

celery_app = Celery(
    "email_risk_ai",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.async_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=os.getenv("APP_TIMEZONE", "UTC"),
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1")),
    result_expires=int(os.getenv("CELERY_RESULT_EXPIRES", "3600")),
    broker_connection_retry_on_startup=True,
    task_time_limit=int(os.getenv("CELERY_TASK_TIME_LIMIT", "300")),
    task_soft_time_limit=int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "240")),
)

# Optional beat schedule. Start with:
# celery -A app.celery_app.celery_app beat -l info
celery_app.conf.beat_schedule = {
    "check-due-followups-every-5-minutes": {
        "task": "app.tasks.check_due_followups",
        "schedule": 300.0,
    },
}
