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
from core.permissions import get_user_with_role
from core.system_config import check_task_limit, check_maintenance_mode
from database.models import Tasks, Conversations, GeometryResults, OptimizationResults, UserRole
from apps.routes.chat import save_message_to_redis, save_or_update_message_in_redis
from apps.geometry import  DifyClient
from apps.geometry import geometry_stream_generator
from apps.retrieval import retrieval_stream_generator
from apps.optimize import optimize_stream_generator
from apps.optimize import AlgorithmClient, write_key
# from apps.celery_tasks import celery_app  # 新增：导入 celery app
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
            
            # 创建算法客户端
            algorithm_client = AlgorithmClient(base_url=settings.OPTIMIZE_API_URL)
            
            # 构建优化配置
            optimization_config = OptimizationConfig(
                task_id=str(task_id),
                model_path=model_path,
                simulation_type=simulation_type,
                population_size=10,  # 可以从参数中读取
                num_generations=10,  # 可以从参数中读取
                lower_bounds=lower_bounds,
                upper_bounds=upper_bounds,
                max_stress=max_stress if simulation_type == "StressSimulation" else None,
                max_volume=max_volume if simulation_type == "FlowSimulation" else None
            )
            
            # 启动优化任务
            task_status = await algorithm_client.start_optimization(optimization_config)
            task.status = task_status.status
            await task.save()
            optimization_started = True
            
            yield f'event: optimization_started\ndata: {json.dumps({"task_id": task_id, "status": task_status.status})}\n\n'
            
            # 9. 轮询Redis获取仿真结果并推送
            last_generation = -1
            processed_evaluations = set()
            
            while True:
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