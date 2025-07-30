from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from fastapi.responses import StreamingResponse
import asyncio
import json

from core.authentication import get_current_active_user, User
from database.models_1 import Tasks, Conversations
from apps.app02 import GenerationMetadata, SSEConversationInfo, SSETextChunk, SSEResponse, FileItem

# 创建一个新的 APIRouter 实例
router = APIRouter(
    prefix="/tasks",
    tags=["任务管理"]
)

# --- Pydantic 模型定义 ---

class TaskCreateRequest(BaseModel):
    """创建新任务的请求体模型"""
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_type: str = Field(..., description="任务类型 (e.g., 'geometry', 'part_retrieval')")
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


# --- API 端点实现 ---

@router.post("", response_model=TaskCreateResponse, summary="创建新任务")
async def create_task(
    task_data: TaskCreateRequest,
    current_user: User = Depends(get_current_active_user)
):
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

    return new_task


@router.post("/execute", summary="执行任务")
async def execute_task(
    request: TaskExecuteRequest,
    current_user: User = Depends(get_current_active_user)
):
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

    # 更新任务状态为“处理中”
    task.status = "processing"
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

                # 任务成功完成，更新状态
                task.status = "completed"
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

    elif request.task_type == "part_retrieval":
        # TODO: 在这里实现零件检索的逻辑
        # 任务成功完成，更新状态
        task.status = "completed"
        await task.save()
        return {"message": "Part retrieval completed", "parts": []}
        
    elif request.task_type == "design_optimization":
        # TODO: 在这里实现设计优化的逻辑
        # 任务成功完成，更新状态
        task.status = "completed"
        await task.save()
        return {"message": "Design optimization completed", "results": {}}

    else:
        task.status = "failed"
        await task.save()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown task type: {request.task_type}"
        )
