from celery import Celery

from app.config import get_settings


def make_celery_app() -> Celery:
    settings = get_settings()
    app = Celery("codebase_assistant", broker=settings.redis_url, backend=settings.redis_url)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_track_started=True,
        worker_prefetch_multiplier=1,
    )
    return app


celery_app = make_celery_app()

# Importing tasks AFTER celery_app exists lets tasks.py's @celery_app.task
# decorator register against this exact instance -- and because this
# module is what `celery -A app.worker.celery_app.celery_app worker`
# loads, the worker process ends up with the task registered automatically
# instead of only the process that happened to call a lazy registration
# function (which is what a `.delay()` call from the API process alone
# would NOT give the separate worker process -- it would reject the task
# as "unregistered").
from app.worker import tasks as _tasks  # noqa: E402,F401
