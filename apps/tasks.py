from typing import Optional, Dict, Any, List
import json
from datetime import datetime
import os
import time 

import sys
import uuid
import redis as redis_sync
import redis.asyncio as redis_async
import asyncio

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
from tortoise.transactions import in_transaction

from core.authentication import get_current_active_user, User
from database.models import Tasks, Conversations, GeometryResults, OptimizationResults
from apps.chat import save_message_to_redis, save_or_update_message_in_redis
from apps.geometry import  DifyClient
from apps.geometry import geometry_stream_generator
from apps.retrieval import retrieval_stream_generator
from apps.optimize import optimize_stream_generator
from apps.optimize import AlgorithmClient, create_task_monitor_callback, write_key
# from apps.celery_tasks import celery_app  # 新增：导入 celery app
from configs.celery_utils import celery
from apps.celery_tasks import celery_optimize_task
from config import settings
from apps.schemas import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskExecuteRequest,
    PendingTaskResponse,
)
from apps.schemas import (
    Message
)
from apps.schemas import (
    AlgorithmRequest,
    OptimizationParamsRequest,
)
from apps.schemas import (
    GenerationMetadata,
    SSEConversationInfo,
    SSETextChunk,
    SSEResponse,
    PartData,
    SSEPartChunk,
    SSEImageChunk
)
from apps.schemas import MessageRequest


# 创建一个新的 APIRouter 实例
router = APIRouter(
    tags=["任务管理"]
)


# # 依赖注入 - 提供算法客户端实例
# async def get_algorithm_client():
#     settings = Settings()
#     client = AlgorithmClient(
#         base_url=settings.OPTIMIZE_API_URL,
#     )
#     try:
#         yield client
#     finally:
#         await client.close()


# --- API 端点实现 ---

@router.get("/pending", response_model=List[PendingTaskResponse], summary="获取所有待处理的任务")
async def get_pending_tasks(
    current_user: User = Depends(get_current_active_user)
):
    """
    获取当前用户所有状态为 'pending' 的任务，并按创建时间升序排列。
    """
    pending_tasks = await Tasks.filter(
        user_id=current_user.user_id,
        status="pending"
    ).order_by("created_at").prefetch_related("conversation")

    # 手动构建响应数据，因为 Pydantic 模型需要 conversation_title
    response_data = [
        PendingTaskResponse(
            task_id=task.task_id,
            task_type=task.task_type,
            created_at=task.created_at,
            conversation_title=task.conversation.title if task.conversation else "未知会话"
        )
        for task in pending_tasks
    ]
    
    return response_data

@router.post("", response_model=TaskCreateResponse, summary="创建新任务")
async def create_task(
    request: Request,
    task_data: TaskCreateRequest,
    current_user: User = Depends(get_current_active_user)
):
    #print("task_data: ", task_data)
    #redis_client = request.app.state.redis
    """
    创建并注册一个新的任务实例。
    
    此接口是所有工作流程的第一步，用于在数据库中生成一个唯一的任务记录。
    """
    # 验证 conversation_id 是否存在且属于当前用户
    conversation = await Conversations.get_or_none(
        conversation_id=task_data.conversation_id, 
        user_id=current_user.user_id
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or does not belong to the current user."
        )
    
    # 创建任务实例
    new_task = await Tasks.create(
        conversation_id=task_data.conversation_id,
        user_id=current_user.user_id,
        task_type=task_data.task_type,
        status="pending", # 初始状态
        #dift_conversation_id="", # 初始为空，后续可更新
        # 'details' 字段在 Tasks 模型中不存在，因此不直接保存
    )
    # 创建任务的文件存放目录
    # 使用配置中的基础目录作为根路径，若未设置则默认使用"files"目录
    base_dir = Path(settings.DIRECTORY) if settings.DIRECTORY else Path("files")
    
    # 构建目标目录路径：上一级目录/files/会话ID
    task_dir = base_dir / str(task_data.conversation_id) / str(new_task.task_id)
    
    try:
        # 创建目录（包括所有必要的父目录）
        task_dir.mkdir(parents=True, exist_ok=True)
        #print(f"成功创建任务目录: {task_dir}")
    except Exception as e:
        print(f"创建任务目录失败: {e}", file=sys.stderr)
        raise
    # 移除在此处保存消息的逻辑，该职责已转移到前端
    # message = Message(
    #     role="user",
    #     content=task_data.details.get("query", ""),
    #     timestamp=datetime.now()
    # )
    # await save_message_to_redis(user_id=current_user.user_id, task_id=new_task.task_id, task_type=task_data.task_type, message=message, redis_client=redis_client)

    return new_task


@router.post("/execute", summary="执行任务")
async def execute_task(
    global_request: Request,  # 使用全局请求对象
    request: TaskExecuteRequest,
    current_user: User = Depends(get_current_active_user)
):
    try:
        # print("request.file_url: ", request.file_url)
        redis_client = global_request.app.state.redis
        # 使用同步 redis 连接用于队列操作 / pubsub（Celery worker 与 SSE generator 共用）
        r_async = redis_async.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB, decode_responses=True)

        """
        根据 task_type 执行一个已创建的任务。
        """
        # print(f"--- Received request to execute task: {request.task_id} ({request.task_type}) ---")
        # 数据库事务
        task = await Tasks.get_or_none(
                task_id=request.task_id, 
                user_id=current_user.user_id
            )
        async with in_transaction() as conn:
            # 验证任务是否存在且属于当前用户
            if not task or task.conversation_id != request.conversation_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Task not found or does not belong to the current user/conversation."
                )

            #print("通过验证了吗")
            # if task.status != "pending":
            #     raise HTTPException(
            #         status_code=status.HTTP_400_BAD_REQUEST,
            #         detail=f"Task {task.task_id} is not in a valid state to start execution. Current state: {task.status}"
            #     )
            # print("通过status验证了吗")
            # 检查是否已经有一个 "optimize" 类型的任务在运行
            if request.task_type == "optimize":
            #     running_optimize_task = await Tasks.filter(
            #         # user_id=current_user.user_id,
            #         task_type="optimize",
            #         status="running"
            #     ).first()
            #     print(running_optimize_task)
                
            #     if running_optimize_task:
            #         print(f"{running_optimize_task.task_id} 任务是运行状态")
            #         raise HTTPException(
            #             status_code=status.HTTP_400_BAD_REQUEST,
            #             detail=f"Task {running_optimize_task.task_id} is already running. Only one 'optimize' task can run at a time."
            #         )

            # 更新任务状态为“处理中”

                task.status = "queued"
                #print("通过optimize验证了吗")
            else:
                task.status = "running"
            await task.save()

        # print("出事务")
        # --- 新增：在执行任务前，保存用户的消息 ---
        if request.query:
            user_message = Message(
                role="user",
                content=request.query,
                timestamp=datetime.now()
            )
            await save_or_update_message_in_redis(
                user_id=current_user.user_id,
                task_id=request.task_id,
                task_type=request.task_type,
                conversation_id=request.conversation_id,
                message=user_message,
                redis_client=redis_client
            )
        # --- 修改结束 ---

        assistant_message = {
            "role": "assistant",
        }

        # 时间戳采用秒级+3位随机数，避免同一秒内冲突
        timestamp = f"{int(time.time())}_{uuid.uuid4().hex[:3]}"

        file_name = f'{current_user.user_id}_{request.conversation_id}_{request.task_id}_{timestamp}'
        
        task.file_name = file_name  # 保存文件名到任务实例中
        await task.save()
        
        combinde_query = request.query #+ f". 我希望生成的.py 和 .step 文件的命名为：{file_name}" 
        # + r'\n请注意文件保存路径为"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\mcp_out"'
        # print("combinde_query: ", combinde_query)
        # 根据任务类型路由到不同的处理逻辑
        
        if request.task_type == "geometry":
            
            return StreamingResponse(
                geometry_stream_generator(
                    request,
                    current_user,
                    redis_client,
                    combinde_query,
                    task
                ), 
                media_type="text/event-stream"
            )

        elif request.task_type == "retrieval":
        
            return StreamingResponse(
                retrieval_stream_generator(
                    request,
                    current_user,
                    redis_client,
                    combinde_query,
                    task
                ), 
                media_type="text/event-stream"
            )


        elif request.task_type == "optimize":
            """
            将 swg_path 指向的单个文件复制到目录。
            如果同名文件已存在，则跳过。
            弃用，算法测已改进
            """
            # swg_path = r"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\machweijfiweowef.swp"
            # if not os.path.isfile(swg_path):
            #     print(f"错误：{swg_path} 不存在或不是文件")
            #     return

            # dst_path = os.path.join(os.path.dirname(request.file_url), os.path.basename(swg_path))

            # if os.path.exists(dst_path):
            #     print(f"跳过：{dst_path} 已存在")
            # else:
            #     shutil.copy2(swg_path, dst_path)   # copy2 保留元数据
            #     print(f"已复制：{swg_path} -> {dst_path}")

            
            # return StreamingResponse(
            #     optimize_stream_generator(
            #         request,
            #         current_user,
            #         redis_client,
            #         combinde_query,
            #         task
            #     ), 
            #     media_type="text/event-stream"
            # )
                    # 为 Celery 提交准备参数
            celery_payload = {
                "task_id": str(request.task_id),
                "conversation_id": str(request.conversation_id),
                "user_id": str(current_user.user_id),
                "file_url": request.file_url or "",
                "query": request.query or "",
                # 将 redis 连接信息序列化传递（不要传 redis 对象本身）
                "redis_host": os.getenv("REDIS_HOST", "host.docker.internal"),
                "redis_port": int(os.getenv("REDIS_PORT", 6379)),
                "redis_db": int(os.getenv("REDIS_DB", 0)),
            }

            # 将 task_id 推入优化队列（fifo）
            queue_key = "optimize_queue"
            try:
                await r_async.rpush(queue_key, task.task_id)
                #print(f"Pushed task {task.task_id} to optimize_queue")
            except Exception as e:
                print("Failed to push task to optimize_queue:", e, file=sys.stderr)
            try:
            # 提交 Celery 任务（异步）
                celery.send_task("optimize:celery_optimize_task", args=[celery_payload], kwargs={})
            except Exception as e:
                print("Failed to submit task to Celery:", e)
                    # 返回一个 SSE 流：先推送队列位置更新，并订阅 worker 发布的 channel
            async def sse_generator():
                try:
                    pubsub =  r_async.pubsub(ignore_subscribe_messages=True)
                    channel = f"optimize_events:{task.task_id}"
                    await pubsub.subscribe(channel)
                    last_pos = None
                    # print("Subscribed to channel:", channel)
                except Exception as e:
                    print("Failed to subscribe to optimize_events channel:", e, file=sys.stderr)
                    yield f"event: error\ndata: {json.dumps({'error': 'Failed to subscribe to optimize_events channel'})}\n\n"
                    return
                try:
                    while True:
                        # 1) 检查队列位置
                        try:
                            queue = await r_async.lrange(queue_key, 0, -1)
                            if str(task.task_id) in queue:
                                pos = queue.index(str(task.task_id)) + 1  # 1-based position
                            else:
                                pos = 0  # 已被 worker 移除 => 已经开始或已结束
                            # print("Current queue:", queue, "Position:", pos)
                        except Exception as e:
                            print("Failed to yield parse_pubsub_message error SSE:", e, file=sys.stderr)
                            pos = -1

                        if pos != last_pos:
                            msg = json.dumps({"type": "queue_position", "position": pos})
                            last_pos = pos
                            yield f"event: queue_update\ndata: {msg}\n\n"
                            
                        
                        # 2) 订阅 channel（非阻塞读取）
                        message = await pubsub.get_message(timeout=1)
                        # print("pubsub message:", message)
                        if message and "data" in message:
                            data = message["data"]
                            # data 本身是 string（Celery worker 将发布完整的 SSE chunk）
                            yield f"{data}\n\n"
                            # 如果 worker 发布结束信号，退出
                            try:
                                payload = json.loads(data.replace("data: ", "") if data.startswith("data: ") else data)
                                if payload.get("event") in ("finished", "failed", "message_end"):
                                    break
                            except Exception as e:
                                print("Failed to yield parse_pubsub_message error SSE:", e, file=sys.stderr)
                        # 小延迟避免忙循环
                        await asyncio.sleep(0.3)
                    # 最后确保取消订阅
                finally:
                    try:
                        await pubsub.unsubscribe(channel)
                        await pubsub.close()
                    except Exception as e:
                        print("pubsub cleanup error:", e, file=sys.stderr)

            return StreamingResponse(sse_generator(), media_type="text/event-stream")



        else:
            #模拟保存生成的消息到数据库, 仅使用示例
            assistant_message["content"] = "Unknown task type. Please check your request."
            # 保存助手消息到Redis
            message = Message(
                role="assistant",
                content=assistant_message["content"],
                timestamp=datetime.now()
            )
            # print("结果回复信息: ", message)
            await save_message_to_redis(
                        user_id=current_user.user_id,
                        task_id=request.task_id,
                        task_type=request.task_type,
                        conversation_id=request.conversation_id,
                        message=message,
                        redis_client=redis_client
                    )
            
            task.status = "failed"
            await task.save()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown task type: {request.task_type}"
            )
    except Exception as e:
        # 更新任务状态为 "failed"
        task.status = "failed"
        await task.save()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Task execution failed: {str(e)}"
        )

@router.post("/optimize/submit-params", summary="提交优化参数")
async def submit_optimization_params(
    request_data: OptimizationParamsRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    接收前端提交的优化参数，并打印。
    """
    # print(f"--- Received optimization parameters for conversation {request_data.conversation_id}, task {request_data.task_id} ---")
    # print("Received Params:", request_data.params)

    # 这里可以添加验证逻辑，例如验证 task_id 和 conversation_id 是否属于当前用户
    task = await Tasks.get_or_none(
        task_id=request_data.task_id,
        user_id=current_user.user_id,
        conversation_id=request_data.conversation_id
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or does not belong to the current user/conversation."
        )
    
    # 查询指定task_id的优化结果
    optimization_result = await OptimizationResults.filter(task_id=request_data.task_id).first()
    model_path = os.path.dirname(optimization_result.optimized_cad_file_path)
    # algorithm_client = AlgorithmClient(base_url=settings.OPTIMIZE_API_URL)
    # # 检查算法服务健康状态
    # health_status = await algorithm_client.check_health()
    # if health_status.status != "healthy":
    #     raise HTTPException(
    #         status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    #         detail="Algorithm service is not healthy."
    #     )
    try:

        #response = await algorithm_client.send_parameter(model_path, request_data.params)
        with open(rf"{model_path}\parameters.txt", "w", encoding="utf-8") as f:
                json.dump(request_data.params, f)
        control_file = os.path.join(model_path, "control.txt")
        write_key(control_file, "command", "8")
        #await algorithm_client.close  ()  # 关闭客户端连接
        # 模拟成功响应
        return {"message": "Parameters received successfully and printed to console."}
    except Exception as e:
        print("Error sending parameters to algorithm service:", e, file=sys.stderr)


@router.get("/optimize/progress/{task_id}")
async def optimize_progress_sse(task_id: str):
    async def event_generator():
        import asyncio
        import json
        import redis as redis_sync

        r = redis_sync.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        channel = f"optimize_events:{task_id}"
        pubsub = r.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(channel)

        queue_key = "optimize_queue"
        last_pos = None
        try:
            while True:
                # 1) 优先读取 pubsub（worker 运行时会发布 started / chunks / finished）
                msg = pubsub.get_message(timeout=1)
                if msg and msg.get("type") == "message":
                    data = msg["data"]
                    if isinstance(data, (bytes, bytearray)):
                        try:
                            data = data.decode("utf-8")
                        except Exception:
                            data = str(data)
                    # 如果是 JSON 描述事件，按 SSE data 发送
                    try:
                        payload = json.loads(data)
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        # 收到结束/失败事件则关闭连接
                        if payload.get("event") in ("message_end", "finished", "failed"):
                            break
                    except Exception:
                        # 不是 JSON，则按原样或包装为 data:
                        if data.startswith("event:") or data.startswith("data:"):
                            yield data if data.endswith("\n\n") else data + "\n\n"
                        else:
                            yield f"data: {data}\n\n"
                    await asyncio.sleep(0)  # 让出控制权，继续循环
                    continue

                # 2) 如果没有 pubsub 消息，周期性检查队列位置（任务还未开始时）
                try:
                    queue = r.lrange(queue_key, 0, -1)
                    if str(task_id) in queue:
                        pos = queue.index(str(task_id)) + 1
                    else:
                        pos = 0
                except Exception:
                    pos = -1

                if pos != last_pos:
                    # 发送自定义事件 queue_update，前端可监听 "queue_update"
                    payload = {"position": pos}
                    yield f"event: queue_update\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    last_pos = pos

                # 小延迟避免忙循环
                await asyncio.sleep(0.2)
        finally:
            try:
                pubsub.unsubscribe(channel)
                pubsub.close()
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/optimize/queue_length")
async def get_optimize_queue_length():
    """
    获取当前优化任务队列的长度。
    """
    r = redis_sync.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    try:
        i = celery.control.inspect()

        # 关键修改：检查 i 是否为 None
        if i is not None:
            # i.active() 和 i.reserved() 可能会返回 None，需要进一步检查
            active_info = i.active()
            reserved_info = i.reserved()
            
            active = sum(len(v) for v in active_info.values()) if active_info else 0
            reserved = sum(len(v) for v in reserved_info.values()) if reserved_info else 0
        else:
            # Celery Worker 不可达
            active = 0
            reserved = 0

        queued = r.llen('optimize')

        # 这里的 reserved + queued 是等待任务的总数
        return {"length": reserved + queued, "running": active}
    except Exception as e:
        # 即使添加了 None 检查，如果 Redis 连接失败等，仍然可能到这里
        print("Failed to fetch optimize queue:", e, file=sys.stderr) 
        # 建议返回一个默认值，而不是 500 错误，以保持前端轮询不中断
        return {"length": -1, "running": 0} # 返回 -1 让前端显示获取失败
        # raise HTTPException(...) # 注释掉 raise HTTPException