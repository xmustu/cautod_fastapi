# from apps.celery import celery_app
from celery import Celery
from apps.optimize import optimize_stream_generator
import redis as redis_sync
import redis.asyncio as redis_async
import asyncio
import json
import time
import os
import copy
from tortoise import Tortoise
from database.settings import TORTOISE_ORM_MYSQL,TORTOISE_ORM_SQLITE
from config import settings
from celery import shared_task
from configs.celery_utils import celery
# celery_app = Celery("cautod",broker = 'pyamqp://admin:admin@localhost:5672//',backend = "redis://127.0.0.1:6379/0")
# @celery_app.task(name="apps.optimize.celery_optimize_task", bind=True)
# @shared_task(bind=True,autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5},
#              name='optimize:celery_optimize_task')
@celery.task(bind=True,autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5},
             name='optimize:celery_optimize_task')
def celery_optimize_task(self, payload):
    """
    在 Celery worker 中运行的任务：
    - 首先把队列中的 task_id 移除（表示已开始）
    - 向 redis pub/sub 发布 started 事件
    - 以异步方式运行 optimize_stream_generator（复用原有逻辑），并把每个 SSE chunk publish 到 channel
    """
    # # test
    # # python
    # import redis, pymysql, socket
    # print("redis ping:", redis.Redis(host="127.0.0.1",port=6379).ping())
    # conn = pymysql.connect(host="127.0.0.1",port=3306,user="lwx",password="i4AIi4AI",db="cautod")
    # print("mysql ok")
    # conn.close()
    # # 主机名解析测试
    # print(socket.getaddrinfo("localhost", 6379))

    task_id = payload.get("task_id")
    file_url = payload.get("file_url")
    conversation_id = payload.get("conversation_id")
    user_id = payload.get("user_id")
    query = payload.get("query", "")
    queue_key = "optimize_queue"
    running_key = "optimize_running"
    channel = f"optimize_events:{task_id}"
    progress_key = f"optimize_progress:{task_id}"
    async def _run_and_publish():
        # 初始化 Tortoise ORM （确保在 worker 中可用）
        if settings.SQLMODE == "MYSQL":
            config = copy.deepcopy(TORTOISE_ORM_MYSQL)
        else:
            config = TORTOISE_ORM_SQLITE
        if  config["connections"]["default"]["credentials"]["host"] == "localhost":
            config["connections"]["default"]["credentials"]["host"] = "127.0.0.1"
        await Tortoise.init(config=config)
        # await Tortoise.generate_schemas()


        # 在异步上下文中创建并使用 async redis 客户端，所有操作都要 await
        redis_host = payload.get("redis_host", os.getenv("REDIS_HOST", "127.0.0.1"))
        # 临时避免 DNS 问题：在 Celery/任务中用 127.0.0.1 替代 localhost
        if redis_host == "localhost":
            redis_host = "127.0.0.1"
        redis_port = payload.get("redis_port", os.getenv("REDIS_PORT", 6379))
        redis_db = payload.get("redis_db", os.getenv("REDIS_DB", 0))
        
        r_async = redis_async.Redis(
            host=redis_host, 
            port=int(redis_port), 
            db=int(redis_db), 
            decode_responses=True
        )
        # r = redis_sync.Redis(host='host.docker.internal', port=6379, db=0, decode_responses=True)
        try:
            # 标记开始：从队列中移除（如果存在）
            try:
                await r_async.lrem(queue_key, 0, task_id)
            except Exception as e:
                print("Warning: lrem failed:", e)
            
            # await r_async.rpush(running_key, task_id)
            # publish started progress
            try:
                await r_async.set(progress_key, json.dumps({"status": "running"}))
                await r_async.publish(channel, json.dumps({"event": "started", "task_id": task_id}))
            except Exception as e:
                print("Warning: publish started failed:", e)
            # 由于 optimize_stream_generator 是 async generator，使用 asyncio.run 在 worker 中执行
            
                # 创建一个 simple redis publisher 客户端用于传递到 async generator（如果需要）
                # 注意：原 generator 接受 redis_client (async?)。我们这里不传入 web app 的 redis，
                # 仅直接遍历 generator 并 publish 每个 chunk 到 redis channel。
                # 创建临时的 asyncio redis/publisher 若需要可以替换为 aioredis。
                
                    # 调用原有 async generator
                    # 需要构造一些 minimal 参数：TaskExecuteRequest-like object 与 Task-like object
            class DummyRequest:
                def __init__(self, conversation_id, task_id, file_url, query):
                    self.conversation_id = conversation_id
                    self.task_id = task_id
                    self.file_url = file_url
                    self.query = query
                    self.task_type = "optimize"

            # 构造 minimal Task 对象兼容 optimize_stream_generator signature
            # 此处只需提供 task_id 和 file_name 等属性被使用到的部分
            class DummyTaskObj:
                def __init__(self, tid):
                    self.task_id = tid
                    self.file_name = ""
                    self.status = "running"
                async def save(self): 
                    return
            # 简单的 user 对象，避免依赖 core.authentication.User 导入
            class DummyUser:
                def __init__(self, user_id, username="worker"):
                    self.user_id = user_id
                    self.username = username

            # 注意：optimize_stream_generator 的实现里使用了 save_or_update_message_in_redis 等 awaitable 函数。
            # 若这些函数依赖于 web app 的 aioredis，则可能需要更多适配；这里假设它们能在 worker 环境下工作或可忽略。
            dummy_request =DummyRequest(conversation_id, task_id, file_url, query)
            dummy_task = DummyTaskObj(task_id)

            # 调用生成器
            agen = optimize_stream_generator(dummy_request, DummyUser(user_id=user_id, username="worker"), r_async, query, dummy_task)  # User 类需能用这个方式构造，或替换为简单对象
            # 如果 above 调用 需改成适合项目的 user 结构，请做对应适配。
            async for chunk in agen:
                # chunk 是字符串 SSE 格式片段，直接 publish
                try:
                    # 保证 string
                    await r_async.publish(channel, chunk)
                except Exception as e:
                    print("publish chunk error:", e)
                    # 仍继续
                    continue
            # 当 generator 结束，写入 finished
            try:
                await r_async.set(progress_key, json.dumps({"status": "finished"}))
                await r_async.publish(channel, json.dumps({"event": "message_end", "task_id": task_id}))
            except Exception as e:
                print("Warning: publish finish failed:", e)
                # 将异常状态 publish 出去

            
        except Exception as e:
            tb = None
            try:
                import traceback
                tb = traceback.format_exc()
            except:
                pass
            try:
                await r_async.set(progress_key, json.dumps({"status": "failed", "error": str(e)}))
                await r_async.publish(channel, json.dumps({"event": "failed", "error": str(e), "traceback": tb, "task_id": task_id}))
            except Exception as pub_e:
                print("Failed to publish error to redis_async:", pub_e)
            raise
        finally:
            # 无论成功或异常，确保从队列中移除该 task_id（避免队列阻塞）
            try:
                await r_async.lrem(queue_key, 0, task_id)
            except Exception as e:
                print("Warning: final lrem failed:", e)

            # try:
            #     await r_async.lrem(running_key, 0, task_id)
            # except Exception as e:
            #     print("Warning: final lrem failed:", e)
            try:
                await r_async.close()
                await r_async.connection_pool.disconnect()
            except Exception:
                pass            
        # 在 celery worker（同步上下文）启动 asyncio 运行
    try:
        asyncio.run(_run_and_publish())
    except Exception as e:
        print("Celery optimize task error:", e)
        raise
    # 在 celery worker（同步上下文）安全地运行异步函数
    # def _run_coroutine_sync(coro_factory):
    #     """
    #     coro_factory: callable that returns a coroutine (例如 lambda: _run_and_publish())
    #     如果当前线程已有运行中的事件循环，则在新线程中使用 asyncio.run() 执行；
    #     否则直接 asyncio.run() 执行。
    #     """
    #     try:
    #         loop = asyncio.get_event_loop()
    #     except RuntimeError:
    #         loop = None

    #     if loop is not None and loop.is_running():
    #         # 当前线程已有运行中的事件循环 —— 在新线程中运行协程
    #         print("Running loop detected, run in new thread")
    #         import concurrent.futures

    #         def _runner():
    #             return asyncio.run(coro_factory())

    #         with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
    #             fut = ex.submit(_runner)
    #             return fut.result()
    #     else:
    #         # 没有运行中的 loop，可以直接运行
    #         print("No running loop, run directly")
    #         return asyncio.run(coro_factory())

    # try:
    #     _run_coroutine_sync(lambda: _run_and_publish())
    # except Exception as e:
    #     print("Celery optimize task error:", e)
    #     raise
    # # 1. 尝试获取当前活跃的事件循环
    # try:
    #     try:
    #         loop = asyncio.get_event_loop()
    #     except RuntimeError:
    #         # 2. 若没有活跃循环，创建新循环（兼容首次调用场景）
    #         loop = asyncio.new_event_loop()
    #         asyncio.set_event_loop(loop)
        
    #     # 3. 在获取/创建的循环中运行异步函数
    #     loop.run_until_complete(_run_and_publish())
    # except Exception as e:
    #     print("Celery optimize task error:", e)
    #     raise
    # # 为每个任务创建全新的事件循环（不复用）
    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)
    
    # try:
    #     # 在独立循环中执行异步任务
    #     loop.run_until_complete(_run_and_publish())
    # finally:
    #     # 任务执行完毕后，彻底关闭循环（关键！）
    #     loop.close()
    #     # 清除当前线程的事件循环引用，避免残留
    #     asyncio.set_event_loop(None)