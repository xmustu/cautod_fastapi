from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from fastapi.responses import StreamingResponse
import asyncio
import json

import redis.asyncio as aioredis
from core.authentication import get_current_active_user, User
from database.models_1 import Tasks
from apps.app02 import SSETextChunk, SSEResponse


from config import Settings
from datetime import datetime
from time import time
# 创建一个新的 APIRouter 实例
router = APIRouter(
    tags=["对话管理"]
)

settings = Settings()

class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    parts: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = "done" # 新增字段，默认为 'done'


def get_message_key(user_id: str, task_id: str) -> str:
    """获取对话在Redis中的键名"""
    return f"message:{user_id}:{task_id}"

def get_user_task_key(user_id: str) -> str:
    """获取用户任务列表在Redis中的键名"""
    return f"user_tasks:{user_id}"


# 保存对话消息
async def save_or_update_message_in_redis(
        user_id: str, 
        task_id: str, 
        task_type: str, 
        conversation_id: str, 
        message:Message, 
        redis_client:aioredis.Redis
        ):
    """
    保存或更新消息到Redis。
    - 如果是用户消息，则总是新增。
    - 如果是助手消息，则更新最新的助手消息快照。
    """
    try:

        message_data = message.model_dump(mode="json")
        message_data["timestamp"] = message.timestamp.timestamp() # 转换为时间戳

        message_key = get_message_key(user_id, task_id)


        if message.role == "assistant":
            # 尝试更新最新的消息（如果是助手消息）
            latest_message_json = await redis_client.lindex(message_key, 0)
            if latest_message_json:
                latest_message = json.loads(latest_message_json)
                if latest_message.get("role") == "assistant":
                    # 更新现有助手消息
                    await redis_client.lset(message_key, 0, json.dumps(message_data))
                else:
                    # 最新的不是助手消息，则新增
                    await redis_client.lpush(message_key, json.dumps(message_data))
            else:
                # 列表为空，直接新增
                await redis_client.lpush(message_key, json.dumps(message_data))
        else:
            # 用户消息总是新增
            await redis_client.lpush(message_key, json.dumps(message_data))

        
        # 更新用户任务列表
        user_task_key = get_user_task_key(user_id)
        task_json = await redis_client.hget(user_task_key, task_id)
        task_info = {
            "task_id": task_id,
            "task_type": task_type,
            "conversation_id": conversation_id, # 新增
            "last_message": message.content, # message.content[:settings.MAX_MESSAGE_LENGTH] + "..." if len(message.content) > settings.MAX_MESSAGE_LENGTH else message.content,
            "last_timestamp": message.timestamp.timestamp()
        }
        await redis_client.hset(user_task_key, task_id, json.dumps(task_info))


    except Exception as e:
        print(f"保存消息失败 - 用户: {user_id}, 任务: {task_id}..., 错误: {e}")
        raise

# 保存对话消息 (保留旧函数以兼容，或标记为废弃)
async def save_message_to_redis(user_id: str, task_id: str, task_type: str, conversation_id: str, message:Message, redis_client:aioredis.Redis):
    # 为保持兼容性，此函数现在直接调用新的更新函数
    await save_or_update_message_in_redis(user_id, task_id, task_type, conversation_id, message, redis_client)

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
                    timestamp=message["timestamp"]
                )) + "\n"
                
                # 保存消息到Redis
                print("保存之前先看看message: ", message)
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
    #user_id: str = Query(..., description="用户ID"),
    task_id: str = Query(..., description="任务ID"),
    current_user: User = Depends(get_current_active_user),
):
    redis_client = request.app.state.redis
    """获取对话历史记录"""

    try:
        history = await get_messages_history(current_user.user_id, task_id, redis_client)
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
    #user_id: str = Query(..., description="用户ID"),
    current_user: User = Depends(get_current_active_user),
):
    redis_client = request.app.state.redis
    """
    获取对话历史记录
    """
    try:
        history = []
        if settings.REDIS_AVAILABLE and redis_client:
            user_task_key = get_user_task_key(current_user.user_id)
            tasks_data = await redis_client.hgetall(user_task_key)

            for task_id, task_info in tasks_data.items():
                task_data =  json.loads(task_info)
                
                last_message_str = task_data.get("last_message", "")
                display_message = last_message_str
                
                # 尝试解析 last_message，如果它是 JSON 并且包含 answer 字段，则只显示 answer
                try:
                    # 首先，尝试将字符串中的事件部分（如 'event: message_end\ndata: '）去掉
                    if last_message_str.startswith('event: message_end'):
                        # 提取 JSON 部分
                        json_str = last_message_str.split('data: ', 1)[1].strip()
                        message_content = json.loads(json_str)
                        if 'answer' in message_content:
                            display_message = message_content['answer']
                    else:
                        # 如果不是 SSE 格式，也尝试直接解析
                        message_content = json.loads(last_message_str)
                        if 'answer' in message_content:
                            display_message = message_content['answer']
                except (json.JSONDecodeError, IndexError, TypeError):
                    # 如果解析失败或格式不符，则保持原始消息
                    display_message = last_message_str

                history.append({
                    "task_id": task_id,
                    "conversation_id": task_data.get("conversation_id"), # 新增
                    "task_type": task_data.get("task_type", "未知类型"),
                    "last_message": display_message,
                    "last_timestamp": task_data.get("last_timestamp", ""),
                    "last_time": datetime.fromtimestamp(task_data["last_timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                })
        else:
            raise NotImplementedError
        
        # 按时间戳降序排序
        history.sort(key=lambda x: x.get('last_timestamp', 0), reverse=True)
        
                             
        return {
            "user_id": current_user.user_id,
            "history": history,
            "total": len(history)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户历史失败: {str(e)}")
    
@router.delete("/message/{task_id}", summary="删除任务的对话历史")
async def delete_task(
    request: Request,
    task_id: str, 
    #user_id:str = Query(..., description="用户ID"),
    current_user: User = Depends(get_current_active_user),
):
    redis_client = request.app.state.redis
    try:
        if settings.REDIS_AVAILABLE and redis_client:
            # 从Redis删除任务历史
            message_key = get_message_key(current_user.user_id, task_id)
            user_task_key = get_user_task_key(current_user.user_id)

            #输出对话历史
            await redis_client.delete(message_key)

            # 删除用户任务列表中的该任务
            await redis_client.hdel(user_task_key, task_id)
        else:
            raise NotImplementedError
        

        return {"message": "任务历史已清除", "task_id": task_id, "user_id": current_user.user_id}
    except Exception as e:

        raise HTTPException(status_code=500, detail="删除会话失败")
    

@router.delete("/history/{task_id}",summary="清除指定任务的对话历史，但保留任务记录")
async def clear_task_history(
    request: Request,
    task_id: str, 
    #user_id: str = Query(..., description="用户ID"),
    current_user: User = Depends(get_current_active_user),
):
    redis_client = request.app.state.redis
    """清除指定任务的对话历史，但保留任务记录"""
    try:
        if settings.REDIS_AVAILABLE and redis_client:
            user_task_key = get_user_task_key(current_user.user_id)
            
            # 1. 获取现有的任务信息
            existing_task_info_str = await redis_client.hget(user_task_key, task_id)
            if not existing_task_info_str:
                raise HTTPException(status_code=404, detail="任务未找到")

            # 2. 从Redis删除对话历史
            message_key = get_message_key(current_user.user_id, task_id)
            await redis_client.delete(message_key)

            # 3. 更新任务信息
            task_data = json.loads(existing_task_info_str)
            task_data["last_message"] = "对话历史已清除"
            task_data["last_timestamp"] = time()

            # 4. 将更新后的信息存回
            await redis_client.hset(user_task_key, task_id, json.dumps(task_data))
        else:
            raise NotImplementedError
        
        return {"message": "对话历史已清除", "task_id": task_id, "user_id": current_user.user_id}

    except Exception as e:
        # 检查是否是自己抛出的HTTPException，如果是，则重新抛出
        if isinstance(e, HTTPException):
            raise e
        # 对于其他未知异常，记录日志并返回通用错误
        print(f"清除对话历史时发生未知错误: {e}")
        raise HTTPException(status_code=500, detail="清除对话历史失败")
