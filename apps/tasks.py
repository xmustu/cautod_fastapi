from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from fastapi.responses import StreamingResponse
import asyncio
import json
from datetime import datetime

from core.authentication import get_current_active_user, User
from database.models_1 import Tasks, Conversations
from apps.app02 import GenerationMetadata, SSEConversationInfo, SSETextChunk, SSEResponse, FileItem
from apps.chat import save_message_to_redis, Message
# 创建一个新的 APIRouter 实例
router = APIRouter(
    tags=["任务管理"]
)

# --- Pydantic 模型定义 ---

class TaskCreateRequest(BaseModel):
    """创建新任务的请求体模型"""
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_type: str = Field(..., description="任务类型 (e.g., 'geometry', 'retrieval')")
    details: Optional[Dict[str, Any]] = Field(None, description="与任务相关的附加信息")

class TaskCreateResponse(BaseModel):
    """创建新任务的响应体模型"""
    task_id: int
    conversation_id: str
    user_id: int
    task_type: str
    status: str
    
    class Config:
        from_attributes = True # Tortoise-ORM 模型实例可以直接转换为 Pydantic 模型

class TaskExecuteRequest(BaseModel):
    """执行任务的请求体模型"""
    task_id: int = Field(..., description="要执行的任务ID")
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_type: str = Field(..., description="任务类型，用于后端路由")
    query: Optional[str] = Field(None, description="用户的文本输入")
    file_url: Optional[str] = Field(None, description="上传文件的URL")
    # ... 其他特定于任务的参数
    files: Optional[List[FileItem]] = Field(None, description="文件列表")

class PendingTaskResponse(BaseModel):
    """待处理任务的响应体模型"""
    task_id: int
    task_type: str
    created_at: datetime
    conversation_title: str

    class Config:
        from_attributes = True


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
    print("task_data: ", task_data)
    redis_client = request.app.state.redis
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
        status="pending" # 初始状态
        # 'details' 字段在 Tasks 模型中不存在，因此不直接保存
    )
    
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
    redis_client = global_request.app.state.redis
    """
    根据 task_type 执行一个已创建的任务。
    """
    print(f"--- Received request to execute task: {request.task_id} ({request.task_type}) ---")
    # 验证任务是否存在且属于当前用户
    task = await Tasks.get_or_none(
        task_id=request.task_id, 
        user_id=current_user.user_id
    )
    if not task or task.conversation_id != request.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or does not belong to the current user/conversation."
        )

    # --- 新增：在执行任务前，保存用户的消息 ---
    if request.query:
        user_message = Message(
            role="user",
            content=request.query,
            timestamp=datetime.now()
        )
        await save_message_to_redis(
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
    # 更新任务状态为“处理中”
    #task.status = "processing"
    task.status = "running"
    await task.save()
    
    # 根据任务类型路由到不同的处理逻辑
    if request.task_type == "geometry":
        # --- 从 app02.py 移植过来的几何建模逻辑 ---
        async def stream_generator():
            try:
                # 首先发送会话和任务信息
                conversation_info_data = SSEConversationInfo(conversation_id=request.conversation_id, task_id=str(request.task_id))
                sse_conv_info = f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'
                yield sse_conv_info

                full_answer = "已根据您的需求生成带孔矩形零件，尺寸符合设计要求。"
                
                # 1. 模拟流式发送文本块
                for i in range(0, len(full_answer), 5):
                    chunk = full_answer[i:i+5]
                    text_chunk_data = SSETextChunk(text=chunk)
                    sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                    yield sse_chunk
                    await asyncio.sleep(0.05)

                # 2. 发送包含完整元数据的结束消息
                final_response_data = SSEResponse(
                    answer=full_answer,
                    metadata=GenerationMetadata(
                        cad_file="https://example.com/generated_model.step",
                        code_file="https://example.com/parametric_model.py",
                        preview_image="https://example.com/preview_image.png"
                    )
                )
                
                sse_final = f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
                yield sse_final

                # 3. 模拟保存生成的消息到数据库
                assistant_message["content"] = sse_final
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

                # 任务成功完成，更新状态
                task.status = "done"
                await task.save()

            except Exception as e:
                # 任务失败，更新状态
                task.status = "failed"
                await task.save()
                # 可以选择性地记录错误日志
                print(f"Error during task execution: {e}")
                # 向客户端发送错误事件
                error_data = json.dumps({"error": "An error occurred during task execution."})
                yield f'event: error\ndata: {error_data}\n\n'

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    elif request.task_type == "retrieval":
        # TODO: 在这里实现零件检索的逻辑
        #模拟保存生成的消息到数据库, 仅使用示例
        assistant_message["content"] = "Part retrieval completed!\n See:"
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
        
        # 任务成功完成，更新状态
        task.status = "done"
        await task.save()
        return {"message": "Part retrieval completed", "parts": []}
        
    elif request.task_type == "optimize":
        async def stream_generator():
            try:
                # 首先发送会话和任务信息
                conversation_info_data = SSEConversationInfo(conversation_id=request.conversation_id, task_id=str(request.task_id))
                sse_conv_info = f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'
                yield sse_conv_info

                full_answer = "已完成机械臂的轻量化设计。根据要求，在满足材料屈服强度为250MPa、安全系数为2（许用应力125MPa）的约束下，我们对机械臂进行了拓扑优化。最终，机械臂质量显著降低，且最大应力点满足安全要求。优化过程的收敛曲线图如下所示。"
                
                # 1. 模拟流式发送文本块
                for i in range(0, len(full_answer), 5):
                    chunk = full_answer[i:i+5]
                    text_chunk_data = SSETextChunk(text=chunk)
                    sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                    yield sse_chunk
                    await asyncio.sleep(0.05)

                # 2. 发送包含完整元数据的结束消息
                final_response_data = SSEResponse(
                    answer=full_answer,
                    metadata=GenerationMetadata(
                        # 提供所有必需的字段，并确保格式正确
                        cad_file="https://example.com/optimized_model.step",
                        code_file="https://example.com/optimization_script.py",
                        preview_image="https://user-images.githubusercontent.com/12345/1000_2000_01.png" # 主预览图
                    )
                )
                
                sse_final = f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
                yield sse_final

                # 3. 保存助手的最终回复到 Redis
                message = Message(
                    role="assistant",
                    content=sse_final, # 保存完整的 SSE 消息
                    timestamp=datetime.now()
                )
                await save_message_to_redis(
                    user_id=current_user.user_id,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    conversation_id=request.conversation_id,
                    message=message,
                    redis_client=redis_client
                )

                # 任务成功完成，更新状态
                task.status = "done"
                await task.save()

            except Exception as e:
                task.status = "failed"
                await task.save()
                print(f"Error during optimization task execution: {e}")
                error_data = json.dumps({"error": "An error occurred during task execution."})
                yield f'event: error\ndata: {error_data}\n\n'

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

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
