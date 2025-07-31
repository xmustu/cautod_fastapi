from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from fastapi.responses import StreamingResponse
import asyncio
import json

from core.authentication import get_current_active_user, User
from database.models_1 import Tasks, Conversations
from apps.app02 import GenerationMetadata, SSEConversationInfo, SSETextChunk, SSEResponse, FileItem

from database.redis import redis_connect
from config import Settings
from datetime import datetime

# 创建一个新的 APIRouter 实例
router = APIRouter(
    prefix="/chat",
    tags=["对话管理"]
)

redis_client = redis_connect()
settings = Settings()

class Message(BaseModel):
    role: str        # 谁说的话："user"(用户) 或 "assistant"(AI)    
    content: str     # 具体的对话内容
    timestamp: datetime = datetime.now()  # 消息的时间戳，默认为当前时间


def get_message_key(user_id: str, task_id: str) -> str:
    """获取对话在Redis中的键名"""
    return f"message:{user_id}:{task_id}"

def get_user_task_ket(user_id: str) -> str:
    """获取用户任务列表在Redis中的键名"""
    return f"user_tasks:{user_id}"


# 保存对话消息
async def save_message_to_redis(user_id: str, task_id: str, message:Message):
    try:
        message_data = {
            "role": message.role,
            "content": message.content,
            "timestamp": message.timestamp,

        }
        if settings.REDIS_AVAILABLE and redis_client:
            #键名
            message_key = get_message_key(user_id, task_id)

            # 将消息添加到对话历史
            redis_client.lpush(message_key, message_data.model_dump_json())

            # 设置过期时间
            #redis_client.expire(key, MESSAGE_EXPIRE_TIME)

            
            # 更新用户任务列表
            user_task_key = get_user_task_ket(user_id)
            task_info = {
                "task_id": task_id,
                "last_message": message.conten, # message.content[:settings.MAX_MESSAGE_LENGTH] + "..." if len(message.content) > settings.MAX_MESSAGE_LENGTH else message.content,
                "last_timestamp": message.timestamp
            }
            redis_client.hset(user_task_key, task_id, task_info.model_dump_json())
        else:
            raise NotImplementedError

    except Exception as e:
        print(f"保存消息失败 - 用户: {user_id}, 任务: {task_id}..., 错误: {e}")
        raise

async def get_messages_history(user_id: str, task_id: str) -> List[Dict[str, Any]]:
    # 从Redis获取对话历史消息
    try:
        if settings.REDIS_AVAILABLE and redis_client:
            message_key = get_message_key(user_id, task_id)
            messages = redis_client.lrange(message_key, 0, -1)

            # 反转消息顺序（Redis中是倒序存储的）
            messages.reverse()

            history = [json.loads(msg) for msg in messages]
            return history
        else:
            raise NotImplementedError
    except Exception as e:
        print(f"获取历史消息失败 - 用户: {user_id}, 任务: {task_id}..., 错误: {e}")
        raise


@router.get("/")
async def page_home():
    """
    对话管理首页
    """
    return {"message": "对话管理首页"}

@router.get("chat/task")
async def get_task_history(
    user_id: str = Query(..., description="用户ID"),
    task_id: str = Query(..., description="任务ID")
):
    """获取对话历史记录"""

    try:
        history = await get_messages_history(user_id, task_id)
        return {
            "task_id": task_id,
            "message": history,
            "total": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取聊天历史失败")

@router.get("/chat/conversation")
async def get_conversation_history(
    user_id: str = Query(..., description="用户ID"),
    task_id: str = Query(..., description="任务ID")
):
    """
    获取对话历史记录
    """
    try:
        history = await get_messages_history(user_id, task_id)
        return {
            "task_id": task_id,
            "messages": history,
            "total": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取会话历史失败: {str(e)}")
    

@router.get("/chat/history")
async def get_user_history(
    user_id: str = Query(..., description="用户ID"),
):
    """
    获取对话历史记录
    """
    try:
        
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户历史失败: {str(e)}")