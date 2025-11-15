
import os

print("current working directory:", os.getcwd())
import redis
from configs.celery_utils import celery
app = celery

i = app.control.inspect()

active = sum(len(v) for v in i.active().values())
reserved = sum(len(v) for v in i.reserved().values())

r = redis.Redis(host='localhost', port=6379, db=0)
queued = r.llen('optimize')

print(f"Active tasks: {active}")
print(f"Reserved tasks: {reserved}")
print(f"Queued tasks in broker: {queued}")
