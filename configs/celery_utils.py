
import os
import time

from celery import current_app as current_celery_app
from celery.result import AsyncResult
from celery.signals import task_postrun

from .celery_config import settings


def create_celery():
    celery_app = current_celery_app
    celery_app.config_from_object(settings, namespace='CELERY')
    celery_app.conf.update(task_track_started=True)
    celery_app.conf.update(task_serializer='pickle')
    celery_app.conf.update(result_serializer='pickle')
    celery_app.conf.update(accept_content=['pickle', 'json'])
    celery_app.conf.update(result_expires=200)
    celery_app.conf.update(result_persistent=True)
    celery_app.conf.update(worker_send_task_events=False)
    celery_app.conf.update(worker_prefetch_multiplier=1)
    celery_app.conf.update(timezone='Asia/Shanghai')

    return celery_app


# 通过环境变量控制：每个任务完成后，worker 休眠的秒数（默认 0 不生效）
_delay_seconds_env = os.environ.get("CELERY_TASK_DELAY", "").strip()
try:
    CELERY_TASK_DELAY_SECONDS = int(_delay_seconds_env) if _delay_seconds_env else 0
except ValueError:
    CELERY_TASK_DELAY_SECONDS = 0


@task_postrun.connect
def delay_after_task(sender=None, **kwargs):
    """
    全局钩子：任意任务在当前 worker 进程执行完成后，统一休眠一段时间。
    - 配置方式：设置环境变量 CELERY_TASK_DELAY（单位：秒，例如 5、10 等）。
    - 注意：建议搭配 worker_prefetch_multiplier=1 和 合理的并发数使用。
    """
    if CELERY_TASK_DELAY_SECONDS > 0:
        time.sleep(CELERY_TASK_DELAY_SECONDS)


def get_task_info(task_id):
    """
    return task info for the given task_id
    """
    task_result = AsyncResult(task_id)
    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": task_result.result
    }
    return result

celery = create_celery()

import apps.celery_tasks 