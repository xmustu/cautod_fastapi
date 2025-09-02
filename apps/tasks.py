from typing import Optional, Dict, Any, List
import json
from datetime import datetime
import os
import time 


import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Request
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
    # 获取当前目录的上一级目录
    parent_dir = Path(os.getcwd())
    
    # 构建目标目录路径：上一级目录/files/会话ID
    task_dir = parent_dir / "files" / str(task_data.conversation_id) / str(new_task.task_id)
    
    try:
        # 创建目录（包括所有必要的父目录）
        task_dir.mkdir(parents=True, exist_ok=True)
        print(f"成功创建任务目录: {task_dir}")
    except Exception as e:
        print(f"创建任务目录失败: {e}")
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
        print("request.file_url: ", request.file_url)
        redis_client = global_request.app.state.redis
        """
        根据 task_type 执行一个已创建的任务。
        """
        print(f"--- Received request to execute task: {request.task_id} ({request.task_type}) ---")
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

            print("通过验证了吗")
            # if task.status != "pending":
            #     raise HTTPException(
            #         status_code=status.HTTP_400_BAD_REQUEST,
            #         detail=f"Task {task.task_id} is not in a valid state to start execution. Current state: {task.status}"
            #     )
            # print("通过status验证了吗")
            # 检查是否已经有一个 "optimize" 类型的任务在运行
            if request.task_type == "optimize":
                running_optimize_task = await Tasks.filter(
                    # user_id=current_user.user_id,
                    task_type="optimize",
                    status="running"
                ).first()
                print(running_optimize_task)
                
                if running_optimize_task:
                    print(f"{running_optimize_task.task_id} 任务是运行状态")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Task {running_optimize_task.task_id} is already running. Only one 'optimize' task can run at a time."
                    )
            print("通过optimize验证了吗")
            # 更新任务状态为“处理中”
            task.status = "running"
            await task.save()

        print("出事务")
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
        print("combinde_query: ", combinde_query)
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

            
            return StreamingResponse(
                optimize_stream_generator(
                    request,
                    current_user,
                    redis_client,
                    combinde_query,
                    task
                ), 
                media_type="text/event-stream"
            )

        else:
            #模拟保存生成的消息到数据库, 仅使用示例
            assistant_message["content"] = "Unknown task type. Please check your request."
            # 保存助手消息到Redis
            message = Message(
                role="assistant",
                content=assistant_message["content"],
                timestamp=datetime.now()
            )
            print("结果回复信息: ", message)
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
    print(f"--- Received optimization parameters for conversation {request_data.conversation_id}, task {request_data.task_id} ---")
    print("Received Params:", request_data.params)

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
        print("Error sending parameters to algorithm service:", e)