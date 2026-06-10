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
        redis_host = payload.get("redis_host", os.getenv("REDIS_HOST", "redis"))
        # 在Docker环境中使用服务名，本地开发时使用localhost
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
            
            # TODO: 这里替换为本地 EXE 调用逻辑
            # 从 payload 获取所需参数
            file_url = payload.get("file_url", "")
            exe_path = os.getenv("OPTIMIZE_EXE_PATH", r"D:\CAutoD\algorithm\optimize\net8.0\sldxunhuan.exe") # 使用默认的exe路径
            exe_exists = os.path.exists(exe_path)
            file_exists = os.path.exists(file_url) if file_url else False
            exe_dir = os.path.dirname(exe_path) if exe_path else ""
            work_dir = os.path.dirname(file_url) if file_url else exe_dir
            print(
                "[optimize] payload: "
                f"task_id={task_id} file_url={file_url} file_exists={file_exists} "
                f"exe_path={exe_path} exe_exists={exe_exists} work_dir={work_dir}"
            )
            if not exe_exists:
                await r_async.set(
                    progress_key,
                    json.dumps({"status": "failed", "error": f"exe not found: {exe_path}"}),
                )
                await r_async.publish(
                    channel,
                    json.dumps(
                        {
                            "event": "failed",
                            "task_id": task_id,
                            "error": f"exe not found: {exe_path}",
                        }
                    ),
                )
                return
            if not file_exists:
                await r_async.set(
                    progress_key,
                    json.dumps({"status": "failed", "error": f"model file not found: {file_url}"}),
                )
                await r_async.publish(
                    channel,
                    json.dumps(
                        {
                            "event": "failed",
                            "task_id": task_id,
                            "error": f"model file not found: {file_url}",
                        }
                    ),
                )
                return
            
            # 使用 asyncio.create_subprocess_exec 异步执行，可以边读边推
            # 注意这里是直接执行 .exe 文件，所以不需要前置 "python" 命令
            cmd = [exe_path, file_url]
            print(f"Executing local optimization cmd: {cmd}")
            
            # 导入包和工具函数
            import asyncio
            from apps.task_utils import check_task_terminated
            
            model_save_path = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=work_dir or None,
                )
                
                async def read_stream(stream):
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        try:
                            line_str = line.decode("utf-8").strip()
                        except UnicodeDecodeError:
                            line_str = line.decode("gbk", errors="replace").strip()
                        if line_str:
                            if line_str.lower().startswith("model save path:"):
                                model_save_path = line_str.split(":", 1)[-1].strip()
                            # 包装成SSE格式
                            chunk = f'event: update\ndata: {{"message": "{line_str}"}}\n\n'
                            try:
                                await r_async.publish(channel, chunk)
                            except Exception as e:
                                print("publish chunk error:", e)

                # 启动控制台输出读取任务
                read_task = asyncio.create_task(read_stream(process.stdout))
                
                while True:
                    # 检查任务是否被终止
                    if await check_task_terminated(r_async, task_id):
                        # 发布终止事件
                        process.kill()
                        try:
                            await r_async.publish(channel, json.dumps({"event": "cancelled", "task_id": task_id, "message": "任务已被用户终止"}))
                            await r_async.set(progress_key, json.dumps({"status": "cancelled", "message": "任务已被用户终止"}))
                        except Exception as e:
                            print(f"发布终止事件失败: {e}")
                        break
                    
                    # 检查进程是否已结束
                    if process.returncode is not None:
                        break
                        
                    await asyncio.sleep(1)
                    
                await read_task
                await process.wait()
            except NotImplementedError:
                print("[optimize] asyncio subprocess not supported, falling back to blocking subprocess")
                import subprocess
                import locale

                def _run_blocking():
                    encoding = locale.getpreferredencoding(False) or "gbk"
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding=encoding,
                        errors="replace",
                        cwd=work_dir or None,
                    )
                    output_lines = []
                    if proc.stdout:
                        for line in proc.stdout:
                            output_lines.append(line.rstrip("\n"))
                    return proc.wait(), output_lines

                return_code, output_lines = await asyncio.to_thread(_run_blocking)
                for line_str in output_lines:
                    if not line_str:
                        continue
                    if line_str.lower().startswith("model save path:"):
                        model_save_path = line_str.split(":", 1)[-1].strip()
                    chunk = f'event: update\ndata: {{"message": "{line_str}"}}\n\n'
                    try:
                        await r_async.publish(channel, chunk)
                    except Exception as e:
                        print("publish chunk error:", e)
                process = None
                class _DummyProc:
                    returncode = return_code
                process = _DummyProc()

            print(f"[optimize] process exited: returncode={process.returncode}")
            if process.returncode not in (0, None):
                try:
                    await r_async.set(
                        progress_key,
                        json.dumps({"status": "failed", "error": f"exe exit code {process.returncode}"}),
                    )
                    await r_async.publish(
                        channel,
                        json.dumps(
                            {
                                "event": "failed",
                                "task_id": task_id,
                                "error": f"exe exit code {process.returncode}",
                            }
                        ),
                    )
                except Exception as e:
                    print("Warning: publish exit code failed:", e)
                return
            
            # 当执行结束，写入 finished
            try:
                await r_async.set(progress_key, json.dumps({"status": "finished"}))
                if model_save_path:
                    await r_async.set(
                        f"optimize_result_path:{task_id}",
                        model_save_path,
                    )
                    try:
                        await r_async.publish(
                            channel,
                            json.dumps(
                                {
                                    "event": "optimize_result",
                                    "task_id": task_id,
                                    "model_save_path": model_save_path,
                                }
                            ),
                        )
                    except Exception as e:
                        print("[optimize] failed to publish optimize_result:", e)
                    try:
                        from database.models import OptimizationResults
                        optimization_result = await OptimizationResults.get_or_none(task_id=task_id)
                        if optimization_result:
                            optimization_result.optimized_cad_file_path = model_save_path
                            await optimization_result.save()
                        else:
                            await OptimizationResults.create(
                                task_id=task_id,
                                optimized_cad_file_path=model_save_path,
                            )
                    except Exception as e:
                        print("[optimize] failed to persist model path:", e)
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_and_publish())
    except Exception as e:
        print("Celery optimize task error:", e)
        raise
    finally:
        try:
            loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(None)
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