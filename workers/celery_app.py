from celery import Celery

from config.settings import get_celery_broker_url


celery_app = Celery(
    "catalogguard",
    broker=get_celery_broker_url(),
    include=["workers.inspection_tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
)
