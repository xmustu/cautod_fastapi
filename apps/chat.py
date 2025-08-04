from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi import Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from fastapi.responses import StreamingResponse
import asyncio
import json

import redis.asyncio as aioredis
from core.authentication import get_current_active_user, User
from database.models_1 import Tasks, Conversations
from apps.app02 import GenerationMetadata, SSEConversationInfo, SSETextChunk, SSEResponse, FileItem


from config import Settings
from datetime import datetime
from time import time
# 创建一个新的 APIRouter 实例
router = APIRouter(
    tags=["对话管理"]
)

settings = Settings()

class Message(BaseModel):
    role: str        # 谁说的话："user"(用户) 或 "assistant"(AI)    
    content: str     # 具体的对话内容
    timestamp: datetime   # 消息的时间戳，默认为当前时间


def get_message_key(user_id: str, task_id: str) -> str:
    """获取对话在Redis中的键名"""
    return f"message:{user_id}:{task_id}"

def get_user_task_key(user_id: str) -> str:
    """获取用户任务列表在Redis中的键名"""
    return f"user_tasks:{user_id}"


# 保存对话消息
async def save_message_to_redis(user_id: str, task_id: str, message:Message, redis_client:aioredis.Redis):
    try:
        print("看看Message: ", message)
        print("role: ", message["role"])
        print("content: ", message["content"])
        print("created_at: ", message["created_at"])
        message_data = {
            "role": message["role"],
            "content": message["content"],
            "timestamp": message["created_at"],

        }
        if settings.REDIS_AVAILABLE and redis_client:
            #键名
            message_key = get_message_key(user_id, task_id)

            # 将消息添加到对话历史
            await redis_client.lpush(message_key, json.dumps(message_data))

            # 设置过期时间
            #redis_client.expire(key, MESSAGE_EXPIRE_TIME)

            
            # 更新用户任务列表
            user_task_key = get_user_task_key(user_id)
            task_info = {
                "task_id": task_id,
                "last_message": message["content"], # message.content[:settings.MAX_MESSAGE_LENGTH] + "..." if len(message.content) > settings.MAX_MESSAGE_LENGTH else message.content,
                "last_timestamp": message["created_at"]
            }
            await redis_client.hset(user_task_key, task_id, json.dumps(task_info))
        else:
            raise NotImplementedError

    except Exception as e:
        print(f"保存消息失败 - 用户: {user_id}, 任务: {task_id}..., 错误: {e}")
        raise

async def get_messages_history(user_id: str, task_id: str, redis_client: aioredis.Redis) -> List[Dict[str, Any]]:
    # 从Redis获取对话历史消息
    try:
        if settings.REDIS_AVAILABLE and redis_client:
            message_key = get_message_key(user_id, task_id)
            messages = await redis_client.lrange(message_key, 0, -1)

            # 反转消息顺序（Redis中是倒序存储的）
            messages.reverse()

            history = [json.loads(msg) for msg in messages]
            return history
        else:
            raise NotImplementedError
    except Exception as e:
        print(f"获取历史消息失败 - 用户: {user_id}, 任务: {task_id}..., 错误: {e}")
        raise

async def generate_stream_respone(
    user_id: str,
    task_id: str,
    user_messages: str,
    redis_client: aioredis.Redis,
):
    """
    生成流式响应
    """
    async def event_generator():
        try:
            # 模拟生成对话内容
            for message in user_messages:
                yield json.dumps(SSETextChunk(
                    role=message["role"],
                    content=message["content"],
                    timestamp=message["created_at"]
                )) + "\n"
                
                # 保存消息到Redis
                await save_message_to_redis(user_id, task_id, message, redis_client)
                
                # 模拟延时
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"生成流式响应失败 - 用户: {user_id}, 任务: {task_id}..., 错误: {e}")
            yield json.dums(SSETextChunk(role="error", content=str(e))) + "\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/")
async def page_home():
    """
    对话管理首页
    """
    return {"message": "对话管理首页"}

@router.post("/stream", summary="流式对话生成", response_model=SSEResponse)
async def chat_stream(request: Request):
    redis_client = request.app.state.redis
    return StreamingResponse(
        generate_stream_respone(request.user_id, request.task_id, request.user_messages, redis_client),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )
@router.get("/task", summary="获取任务的对话历史")
async def get_task_history(
    request: Request,
    user_id: str = Query(..., description="用户ID"),
    task_id: str = Query(..., description="任务ID"),
):
    redis_client = request.app.state.redis
    """获取对话历史记录"""

    try:
        history = await get_messages_history(user_id, task_id, redis_client)
        return {
            "task_id": task_id,
            "message": history,
            "total": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取聊天历史失败")


@router.get("/history",summary="获取用户对话历史记录")
async def get_user_history(
    request: Request,
    user_id: str = Query(..., description="用户ID"),
):
    redis_client = request.app.state.redis
    """
    获取对话历史记录
    """
    try:
        history = []
        if settings.REDIS_AVAILABLE and redis_client:
            user_task_key = get_user_task_key(user_id)
            tasks_data = await redis_client.hgetall(user_task_key)

            for task_id, task_info in tasks_data.items():
                task_data =  json.loads(task_info)
                history.append({
                    "task_id": task_id,
                    "last_message": task_data.get("last_message", ""),
                    "last_timestamp": task_data.get("last_timestamp", ""),
                    "last_time": datetime.fromtimestamp(task_data["last_timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                })
        else:
            raise NotImplementedError
        
        return {
            "user_id": user_id,
            "history": history,
            "total": len(history)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户历史失败: {str(e)}")
    
@router.delete("/message/{task_id}", summary="删除任务的对话历史")
async def delete_task(
    request: Request,
    task_id: str, 
    user_id:str = Query(..., description="用户ID"),
):
    redis_client = request.app.state.redis
    try:
        if settings.REDIS_AVAILABLE and redis_client:
            # 从Redis删除任务历史
            message_key = get_message_key(user_id, task_id)
            user_task_key = get_user_task_key(user_id)

            #输出对话历史
            await redis_client.delete(message_key)

            # 删除用户任务列表中的该任务
            await redis_client.hdel(user_task_key, task_id)
        else:
            raise NotImplementedError
        
        return {"message": "任务历史已清除", "task_id": task_id, "user_id": user_id}
    except Exception as e:

        raise HTTPException(status_code=500, detail="删除会话失败")
    

@router.delete("/history/{task_id}",summary="清除指定任务的对话历史，但保留任务记录")
async def clear_task_history(
    request: Request,
    task_id: str, 
    user_id: str = Query(..., description="用户ID"),
):
    redis_client = request.app.state.redis
    """清除指定任务的对话历史，但保留任务记录"""
    try:
        if settings.REDIS_AVAILABLE and redis_client:
            # 从Redis删除对话历史
            message_key = get_message_key(user_id, task_id)

            #删除对话历史
            await redis_client.delete(message_key)

            # 更新任务信息， 保留任务单清空最后消息
            user_task_key = get_user_task_key(user_id)
            task_info = {
                "task_id": task_id,
                "last_message": "",
                "last_timestamp": time.time()
            }
            await redis_client.hset(user_task_key, task_id, json.dumps(task_info))
        else:
            raise NotImplementedError

    except Exception as e:
          raise HTTPException(status_code=500, detail="清除对话历史失败")