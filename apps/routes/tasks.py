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
from starlette.requests import ClientDisconnect
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
from tortoise.transactions import in_transaction
from core.authentication import get_current_active_user, User
from core.permissions import get_user_with_role
from core.system_config import check_task_limit, check_maintenance_mode
from core.permissions import PermissionChecker
from database.models import Tasks, Conversations, GeometryResults, OptimizationResults, UserRole
from apps.routes.chat import save_message_to_redis, save_or_update_message_in_redis
from apps.providers.geometry_provider import geometry_stream_by_provider
from apps.retrieval import retrieval_stream_generator
from apps.optimize import optimize_stream_generator
from apps.optimize import AlgorithmClient, write_key
from configs.celery_utils import celery
from apps.celery_tasks import celery_optimize_task
from config import settings
from apps.schemas import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskExecuteRequest,
    PendingTaskResponse,
    TaskResponse,
    TaskListRequest,
    TaskCancelResponse,
    TaskCancelRequest,
)
from apps.schemas import (
    Message
)
from apps.schemas import (
    AlgorithmRequest,
    OptimizationParamsRequest,
    OptimizationInitialParamsRequest,
    AlgorithmRecommendRequest,
    AlgorithmRecommendResponse,
    AlgorithmRecommendation,
)
from apps.providers.agent_client import AgentServiceClient
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
from apps.task_utils import (
    cancel_task_execution,
    normalize_cancel_mode,
    normalize_cancel_reason,
    register_celery_task_mapping,
)


# 创建一个新的 APIRouter 实例
router = APIRouter(
    tags=["任务管理"]
)


# --- API 端点实现 ---

@router.post("/list", response_model=List[TaskResponse], summary="获取任务列表")
async def get_tasks(
    request_data: TaskListRequest,
    user_info: tuple = Depends(get_user_with_role)
):
    """
    获取任务列表（支持筛选和分页）
    
    权限控制：
    - 普通用户：只能看自己的任务
    - 高级用户：只能看自己的任务（但可能有更详细信息）
    - 管理员：可以看所有用户的任务
    
    请求体示例：
    ```json
    {
        "task_type": "geometry",
        "status": "completed",
        "limit": 20,
        "offset": 0
    }
    ```
    
    所有字段都是可选的：
    - 不指定筛选条件则返回所有任务
    - limit 默认 50，最大 100
    - offset 默认 0，用于分页
    """
    current_user, role = user_info
    
    # 构建查询
    if role == UserRole.ADMIN:
        # 管理员可以看所有任务
        tasks_query = Tasks.all()
    else:
        # 普通用户和高级用户只能看自己的任务
        tasks_query = Tasks.filter(user_id=current_user.user_id)
    
    # 应用筛选条件
    if request_data.task_type:
        tasks_query = tasks_query.filter(task_type=request_data.task_type)
    if request_data.status:
        tasks_query = tasks_query.filter(status=request_data.status)
    
    # 分页和排序
    tasks = await tasks_query.order_by("-created_at").offset(request_data.offset).limit(request_data.limit)
    
    return tasks

@router.get("/pending", response_model=List[PendingTaskResponse], summary="获取所有待处理的任务")
async def get_pending_tasks(
    current_user: User = Depends(check_maintenance_mode)
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
    current_user: User = Depends(check_maintenance_mode)
):
    #print("task_data: ", task_data)
    #redis_client = request.app.state.redis
    """
    创建并注册一个新的任务实例。
    
    此接口是所有工作流程的第一步，用于在数据库中生成一个唯一的任务记录。
    """
    # 检查用户任务数量限制
    await check_task_limit(current_user.user_id)
    
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
    current_user: User = Depends(check_maintenance_mode)
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

            # 更新任务状态为"处理中"

                task.status = "pending"
                print(f"[optimize] set task status pending: task_id={task.task_id}")
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
                geometry_stream_by_provider(
                    global_request,
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
                    global_request,
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
            print(
                f"[optimize] execute request: task_id={request.task_id} file_url={request.file_url} user_id={current_user.user_id}"
            )
            selected_params = {}

            celery_payload = {
                "task_id": str(request.task_id),
                "conversation_id": str(request.conversation_id),
                "user_id": str(current_user.user_id),
                "file_url": request.file_url or "",
                "query": request.query or "",
                "selected_params": selected_params,
                # 将 redis 连接信息序列化传递（不要传 redis 对象本身）
                "redis_host": os.getenv("REDIS_HOST", settings.REDIS_HOST),
                "redis_port": int(os.getenv("REDIS_PORT", settings.REDIS_PORT)),
                "redis_db": int(os.getenv("REDIS_DB", settings.REDIS_DB)),
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
                print(f"[optimize] submit celery task payload keys: {list(celery_payload.keys())}")
                celery_result = celery.send_task("optimize:celery_optimize_task", args=[celery_payload], kwargs={})
                await register_celery_task_mapping(r_async, task.task_id, celery_result.id)
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
                        if await global_request.is_disconnected():
                            await cancel_task_execution(
                                task=task,
                                redis_client=r_async,
                                reason="page_leave",
                                mode="graceful",
                                actor_user_id=current_user.user_id,
                            )
                            break
                        # 1) 检查队列位置
                        # try:
                        #     queue = await r_async.lrange(queue_key, 0, -1)
                        #     if str(task.task_id) in queue:
                        #         pos = queue.index(str(task.task_id)) + 1  # 1-based position
                        #     else:
                        #         pos = 0  # 已被 worker 移除 => 已经开始或已结束
                        #     # print("Current queue:", queue, "Position:", pos)
                        # except Exception as e:
                        #     print("Failed to yield parse_pubsub_message error SSE:", e, file=sys.stderr)
                        #     pos = -1

                        # if pos != last_pos:
                        #     msg = json.dumps({"type": "queue_position", "position": pos})
                        #     last_pos = pos
                        #     yield f"event: queue_update\ndata: {msg}\n\n"
                            
                        
                        # 2) 订阅 channel（非阻塞读取）
                        message = await pubsub.get_message(timeout=1)
                        # print("pubsub message:", message)
                        if message and "data" in message:
                            data = message["data"]
                            # data 本身是 string（Celery worker 将发布完整的 SSE chunk）
                            print("Yielding SSE data:", data)
                            if "started" not in data:  # 过滤掉订阅确认消息
                                yield f"{data}\n\n"
                            # 如果 worker 发布结束信号，退出
                            try:
                                normalized = data.strip()
                                # SSE update chunks (event: update\n...) 不是 JSON，跳过解析
                                if normalized.startswith("event:"):
                                    continue
                                if normalized.startswith("{"):
                                    payload = json.loads(normalized)
                                    if payload.get("event") in ("finished", "failed", "message_end"):
                                        break
                            except Exception as e:
                                print("Failed to yield parse_pubsub_message error SSE:", e, file=sys.stderr)
                        # 小延迟避免忙循环
                        await asyncio.sleep(0.3)
                except (asyncio.CancelledError, BrokenPipeError, ClientDisconnect):
                    await cancel_task_execution(
                        task=task,
                        redis_client=r_async,
                        reason="page_leave",
                        mode="graceful",
                        actor_user_id=current_user.user_id,
                    )
                    raise
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
        import traceback
        traceback.print_exc()
        print(f"Error in execute_task: {str(e)}")
        # 更新任务状态为 "failed"
        if 'task' in locals() and task:
            try:
                task.status = "failed"
                await task.save()
            except Exception as inner_e:
                print(f"Failed to update task status: {inner_e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Task execution failed: {str(e)}"
        )

async def _cancel_task_impl(
    request: Request,
    task_id: int,
    body: TaskCancelRequest,
    current_user: User = Depends(check_maintenance_mode)
):
    """
    无条件终止正在运行的任务，释放后端资源，并通知功能模块做出终止响应。
    
    权限控制：
    - 普通用户：只能终止自己的任务
    - 管理员：可以终止任何任务
    
    支持的任务类型：
    - optimize: Celery 异步任务
    - geometry: 流式任务
    - retrieval: 流式任务
    
    终止操作包括：
    1. 检查任务状态（只能终止 running/queued 状态的任务）
    2. 对于 Celery 任务，revoke 任务
    3. 对于流式任务，通过 Redis 设置终止标志
    4. 更新任务状态为 cancelled
    5. 清理 Redis 中的相关数据
    6. 通知功能模块终止任务（通过 Redis pub/sub）
    """
    # 检查用户是否为管理员
    is_admin = await PermissionChecker.is_admin(current_user.email)
    
    # 获取任务
    task = await Tasks.get_or_none(task_id=task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 权限验证：普通用户只能终止自己的任务
    if not is_admin and task.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限终止此任务"
        )
    
    reason = normalize_cancel_reason(body.reason)
    mode = normalize_cancel_mode(body.mode)

    r_async = None
    try:
        r_async = redis_async.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        cancel_result = await cancel_task_execution(
            task=task,
            redis_client=r_async,
            reason=reason,
            mode=mode,
            actor_user_id=current_user.user_id,
        )
        return TaskCancelResponse(
            task_id=task_id,
            status=cancel_result["status"],
            message="任务已终止（幂等）" if cancel_result["already_cancelled"] else "任务已成功终止",
            cancelled_at=datetime.now()
        )
        
    except Exception as e:
        print(f"终止任务时发生错误: {e}")
        # 即使终止操作失败，也尝试更新任务状态
        try:
            task.status = "cancelled"
            await task.save()
        except:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"终止任务失败: {str(e)}"
        )
    finally:
        if r_async:
            try:
                await r_async.close()
                await r_async.connection_pool.disconnect()
            except Exception:
                pass


@router.post("/{task_id}/cancel", response_model=TaskCancelResponse, summary="终止正在运行的任务（标准路径）")
async def cancel_task_v2(
    request: Request,
    task_id: int,
    body: TaskCancelRequest = TaskCancelRequest(),
    current_user: User = Depends(check_maintenance_mode),
):
    return await _cancel_task_impl(request, task_id, body, current_user)


@router.post("/cancel/{task_id}", response_model=TaskCancelResponse, summary="终止正在运行的任务（兼容路径）", deprecated=True)
async def cancel_task_legacy(
    request: Request,
    task_id: int,
    body: TaskCancelRequest = TaskCancelRequest(),
    current_user: User = Depends(check_maintenance_mode),
):
    return await _cancel_task_impl(request, task_id, body, current_user)


def _normalize_recommendations(payload: Any) -> List[AlgorithmRecommendation]:
    recommendations: List[AlgorithmRecommendation] = []

    def _append(item: Any) -> None:
        if isinstance(item, str):
            recommendations.append(AlgorithmRecommendation(algorithm=item))
            return
        if isinstance(item, dict):
            algorithm = item.get("algorithm") or item.get("name") or item.get("method")
            if algorithm:
                recommendations.append(
                    AlgorithmRecommendation(
                        algorithm=str(algorithm),
                        reason=item.get("reason"),
                        score=item.get("score"),
                    )
                )

    if isinstance(payload, dict):
        data = payload.get("data") if "data" in payload else payload
        items = data.get("recommendations") if isinstance(data, dict) else None
        if isinstance(items, list):
            for item in items:
                _append(item)
    elif isinstance(payload, list):
        for item in payload:
            _append(item)

    if not recommendations:
        for fallback in ("GA", "PSO", "DE"):
            recommendations.append(AlgorithmRecommendation(algorithm=fallback))

    return recommendations


@router.post("/optimize/recommend-algorithms", response_model=AlgorithmRecommendResponse, summary="推荐优化算法")
async def  recommend_optimization_algorithms(
    request_data: AlgorithmRecommendRequest,
    current_user: User = Depends(check_maintenance_mode)
):
    """
    在用户选择优化参数后，调用推荐 Agent 返回推荐算法列表。
    不改变现有优化任务流，只提供额外推荐步骤供前端调用。
    """
    task = await Tasks.get_or_none(
        task_id=request_data.task_id,
        user_id=current_user.user_id,
        conversation_id=request_data.conversation_id,
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or does not belong to the current user/conversation.",
        )

    optimization_result = await OptimizationResults.filter(task_id=request_data.task_id).first()
    model_path = optimization_result.optimized_cad_file_path if optimization_result else None

    client = AgentServiceClient()
    payload = {
        "task_id": str(request_data.task_id),
        "conversation_id": str(request_data.conversation_id),
        "selected_params": request_data.selected_params,
        "model_path": model_path,
    }
    try:
        agent_payload = await client.recommend_algorithms(
            payload,
            session_id=getattr(task, "dify_conversation_id", None),
        )
        recommendations = _normalize_recommendations(agent_payload)
        provider = "agent"
    except Exception as exc:
        print(f"Algorithm recommend agent failed: {exc}", file=sys.stderr)
        recommendations = _normalize_recommendations({})
        provider = "fallback"

    return AlgorithmRecommendResponse(
        task_id=request_data.task_id,
        recommendations=recommendations,
        provider=provider,
    )

@router.post("/optimize/submit-params", summary="提交优化参数")
async def submit_optimization_params(
    request_data: OptimizationParamsRequest,
    current_user: User = Depends(check_maintenance_mode)
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
    model_path = None
    if optimization_result and optimization_result.optimized_cad_file_path:
        model_path = Path(os.path.dirname(optimization_result.optimized_cad_file_path))
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
        # 保存到 Redis，供 execute 阶段读取并传递给本地 EXE
        params_key = f"optimize_params:{request_data.task_id}"
        r_async = redis_async.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
        await r_async.set(params_key, json.dumps(request_data.params))
        await r_async.close()

        # 若存在老流程的模型目录则继续写文件（兼容）
        if model_path:
            params_file = model_path / "parameters.txt"
            with open(params_file, "w", encoding="utf-8") as f:
                json.dump(request_data.params, f)
            control_file = model_path / "control.txt"
            write_key(control_file, "command", "8")
            print(f"Optimization parameters saved to {params_file} and control command set to 8 in {control_file}.")
        #await algorithm_client.close  ()  # 关闭客户端连接
        # 模拟成功响应
        return {"message": "Parameters received successfully and printed to console."}
    except Exception as e:
        print("Error sending parameters to algorithm service:", e, file=sys.stderr)


@router.post("/optimize/initial-params", summary="获取优化初始参数")
async def get_optimization_initial_params(
    request_data: OptimizationInitialParamsRequest,
    current_user: User = Depends(check_maintenance_mode),
):
    task = await Tasks.get_or_none(
        task_id=request_data.task_id,
        user_id=current_user.user_id,
        conversation_id=request_data.conversation_id,
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or does not belong to the current user/conversation.",
        )

    from apps.optimize import AlgorithmClient, GetInitialParametersRequest

    algorithm_client = AlgorithmClient(base_url=settings.OPTIMIZE_API_URL)
    initial_request = GetInitialParametersRequest(
        task_id=str(request_data.task_id),
        model_path=request_data.file_url,
        simulation_type=request_data.simulation_type or "StressSimulation",
    )
    try:
        initial_params_result = await algorithm_client.get_initial_parameters(initial_request)
        initial_parameters = initial_params_result.get("parameters")
        if initial_parameters is None:
            legacy_params = initial_params_result.get("initial_parameters", {})
            if isinstance(legacy_params, dict):
                initial_parameters = [
                    {
                        "name": name,
                        "min": float(value),
                        "max": float(value),
                        "initial": float(value),
                    }
                    for name, value in legacy_params.items()
                ]
            else:
                initial_parameters = []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get initial parameters: {str(e)}",
        )

    return {"parameters": initial_parameters}


@router.get("/optimize/progress/{task_id}")
async def optimize_progress_sse(task_id: str):
    """
    优化进度SSE接口
    流程：
    1. 检查参数是否已提交
    2. 如果已提交，启动优化任务
    3. 轮询Redis获取仿真结果并推送
    """
    async def event_generator():
        import asyncio
        import json
        import redis.asyncio as redis_async
        from apps.optimize import AlgorithmClient, OptimizationConfig
        from database.models import Tasks, OptimizationResults
        from apps.routes.chat import save_or_update_message_in_redis
        from apps.schemas import Message, SSETextChunk, SSEResponse, GenerationMetadata
        
        r_async = redis_async.Redis(
            host=settings.REDIS_HOST, 
            port=settings.REDIS_PORT, 
            db=settings.REDIS_DB, 
            decode_responses=True
        )
        
        algorithm_client = None
        optimization_started = False
        
        try:
            # 获取任务信息
            task = await Tasks.get_or_none(task_id=task_id)
            if not task:
                yield f'event: error\ndata: {json.dumps({"error": "Task not found"})}\n\n'
                return
            
            # 获取优化结果以获取模型路径
            optimization_result = await OptimizationResults.get_or_none(task_id=task_id)
            if not optimization_result:
                yield f'event: error\ndata: {json.dumps({"error": "Optimization result not found"})}\n\n'
                return
            
            model_path = optimization_result.optimized_cad_file_path
            model_dir = Path(model_path).parent if model_path else Path(".")
            params_file = model_dir / "parameters.txt"
            
            # 7. 等待前端提交参数
            max_wait_time = 300  # 最多等待5分钟
            wait_start = time.time()
            
            while not params_file.exists():
                if time.time() - wait_start > max_wait_time:
                    yield f'event: error\ndata: {json.dumps({"error": "Timeout waiting for parameters"})}\n\n'
                    return
                await asyncio.sleep(1)  # 每秒检查一次
            
            # 8. 读取用户提交的参数并启动优化任务
            try:
                with open(params_file, "r", encoding="utf-8") as f:
                    params_data = json.load(f)
            except Exception as e:
                yield f'event: error\ndata: {json.dumps({"error": f"Failed to read parameters: {str(e)}"})}\n\n'
                return
            
            # 解析参数
            lower_bounds = {}
            upper_bounds = {}
            simulation_type = "StressSimulation"
            max_stress = 2.5e8
            max_volume = None
            
            for param_name, param_info in params_data.items():
                if isinstance(param_info, dict):
                    if "min" in param_info:
                        lower_bounds[param_name] = float(param_info["min"])
                    if "max" in param_info:
                        upper_bounds[param_name] = float(param_info["max"])
                    if "simulation_type" in param_info:
                        simulation_type = param_info["simulation_type"]
                    if "max_stress" in param_info:
                        max_stress = float(param_info["max_stress"])
                    if "max_volume" in param_info:
                        max_volume = float(param_info["max_volume"])
            
            if not lower_bounds or not upper_bounds:
                yield f'event: error\ndata: {json.dumps({"error": "Invalid parameters: missing bounds"})}\n\n'
                return
            
            # 创建算法客户端 (本地EXE形式将在这里使用不同的调用，但为了兼容仍保留客户端或使用 Celery 执行)
            # 不过我们已经收到参数，可以正式开始优化流程了
            
            # 使用 Celery 异步任务启动本地优化执行代码
            from apps.celery_tasks import celery_optimize_task
            
            try:
                # 调用 Celery，它内部通过 subprocess.run 执行本地 exe 逻辑
                celery_optimize_task.delay({
                    "task_id": str(task_id),
                    "file_url": model_path,
                    "conversation_id": str(task.conversation_id),
                    "user_id": task.user_id,
                    "query": "",  # 可以根据需要传递额外参数
                    "selected_params": params_data,  # 新增：传递用户选择的优化参数
                })
            except Exception as e:
                yield f'event: error\ndata: {json.dumps({"error": f"Failed to start celery task: {str(e)}"})}\n\n'
                return
            
            optimization_started = True
            
            # 等待一小段时间让 celery 任务开始，然后进入轮询 redis 拿进度
            await asyncio.sleep(1)
            # 启动优化任务 (这里直接 yield started，然后进入 Redis 轮询)
            yield f'event: optimization_started\ndata: {json.dumps({"task_id": task_id, "status": "running"})}\n\n'
            
            # 9. 轮询Redis获取仿真结果并推送
            last_generation = -1
            processed_evaluations = set()
            
            while True:
                # 检查任务是否被终止
                terminate_key = f"task_terminate:{task_id}"
                is_terminated = await r_async.get(terminate_key)
                if is_terminated:
                    yield f'event: cancelled\ndata: {json.dumps({"task_id": task_id, "message": "任务已被终止"})}\n\n'
                    break
                
                # 检查任务状态
                status_data = await algorithm_client.get_optimization_status(str(task_id))
                
                if status_data.status == "completed":
                    # 任务完成，获取最终结果
                    result = await algorithm_client.get_optimization_result(str(task_id))
                    
                    result_text = f"\n\n优化任务已完成！\n最佳适应度: {result.get('best_fitness', 'N/A')}\n"
                    text_chunk_data = SSETextChunk(text=result_text)
                    yield f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                    
                    # 发送完成事件
                    final_metadata = GenerationMetadata(
                        cad_file=model_path,
                        code_file="",
                        preview_image=None
                    )
                    final_response_data = SSEResponse(
                        answer=result_text,
                        metadata=final_metadata
                    )
                    yield f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
                    break
                    
                elif status_data.status == "failed":
                    error_msg = status_data.message or "优化任务失败"
                    error_text = f"\n\n**任务执行出错**: {error_msg}\n"
                    text_chunk_data = SSETextChunk(text=error_text)
                    yield f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                    yield f'event: error\ndata: {json.dumps({"error": error_msg})}\n\n'
                    break
                
                # 获取优化进度数据
                progress = await algorithm_client.get_optimization_progress(str(task_id))
                
                # 处理新的一代数据
                if progress.current_generation > last_generation:
                    for gen_data in progress.data:
                        if gen_data.generation > last_generation:
                            # 发送新的一代数据
                            gen_text = f"第 {gen_data.generation} 代，排名 {gen_data.rank}，适应度: {gen_data.fitness:.6e}"
                            if gen_data.cv > 0:
                                gen_text += f"，约束违反: {gen_data.cv:.2e}"
                            gen_text += "\n"
                            
                            text_chunk_data = SSETextChunk(text=gen_text)
                            yield f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                    
                    last_generation = progress.current_generation
                
                # 处理实时评估数据
                try:
                    eval_list = await r_async.lrange(f"task:{task_id}:evaluations", 0, -1)
                    for eval_item in eval_list:
                        eval_data = json.loads(eval_item)
                        eval_id = eval_data.get("eval_id")
                        if eval_id and eval_id not in processed_evaluations:
                            processed_evaluations.add(eval_id)
                            # 可以在这里发送实时评估数据
                            pass
                except Exception as e:
                    print(f"读取评估数据出错: {e}")
                
                # 等待一段时间后再次检查
                await asyncio.sleep(2)
                
        except Exception as e:
            print(f"Error in optimize_progress_sse: {e}")
            import traceback
            traceback.print_exc()
            yield f'event: error\ndata: {json.dumps({"error": str(e)})}\n\n'
        finally:
            if algorithm_client:
                try:
                    await algorithm_client.close()
                except:
                    pass
            try:
                await r_async.close()
                await r_async.connection_pool.disconnect()
            except:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/optimize/queue_length")
async def get_optimize_queue_length():
    """
    获取当前优化任务队列的长度。
    """
    r = redis_sync.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB, decode_responses=True)
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
