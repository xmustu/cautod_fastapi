from celery.result import AsyncResult
from apps.celery_tasks import celery_app

task_id = "61dd210b-4c6e-4f53-973a-73c154e6c620"
res = AsyncResult(task_id, app=celery_app)
print("状态:", res.status)
print("结果:", res.result)
print("traceback:", res.traceback)  # 若任务失败，会有 traceback 字符串