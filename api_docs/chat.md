# apps.chat 模块 API 文档

路由前缀：`/api/chat`  （来自 main.py 中 app.include_router(chat_router, prefix="/api/chat")）

说明：对话（聊天）管理相关接口与 Redis 消息历史管理。

## GET /
- 方法：GET
- 路由：/
- 描述：对话管理首页
- 鉴权：公开

## POST /stream
- 方法：POST
- 路由：/stream
- 描述：流式对话生成接口，返回 SSE (SSEResponse)
- 鉴权：请求体中需包含相应字段（方法签名为接受 Request），典型由前端打开 SSE 连接
- 响应：StreamingResponse (text/event-stream)
- 备注：内部实现会调用 save_or_update_message_in_redis 存储消息并发送事件：conversation_info, text_chunk, part_chunk, image_chunk, message_end 等

## GET /task?task_id=...
- 方法：GET
- 路由：/task
- 描述：获取指定任务的对话历史（从 Redis 读取）
- 鉴权：需要登录
- 请求参数：task_id (query)
- 响应：{"task_id":..., "message": [...], "total": n}

## GET /history
- 方法：GET
- 路由：/history
- 描述：获取当前用户的对话历史（基于 Redis 中 user_tasks 哈希）
- 鉴权：需要登录
- 响应：{"user_id": ..., "history": [...], "total": n}

## DELETE /message/{task_id}
- 方法：DELETE
- 路由：/message/{task_id}
- 描述：删除当前用户某任务的对话历史（删除 Redis 列表与 user_tasks 哈希条目）
- 鉴权：需要登录
- 响应：{"message": "任务历史已清除", "task_id": ..., "user_id": ...}

## DELETE /history/{task_id}
- 方法：DELETE
- 路由：/history/{task_id}
- 描述：清除指定任务的对话历史，但保留任务记录（更新 user_tasks 中的 last_message 与 last_timestamp）
- 鉴权：需要登录

---

备注：Redis 必须可用并在 app.state.redis 中注册，设置项为 settings.REDIS_AVAILABLE 等。