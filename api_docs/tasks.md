# apps.tasks 模块 API 文档

路由前缀：`/api/tasks`  （来自 main.py 中 app.include_router(tasks_router, prefix="/api/tasks")）

说明：列出 `apps/tasks.py` 中的任务管理相关路由与行为。

## POST /list
- 方法：POST
- 路由：/list
- 描述：获取任务列表（支持筛选与分页）
- 鉴权：需要登录（通过 get_user_with_role 获取当前用户和角色）
- 权限：管理员可查看所有任务，普通/高级用户只能查看自己的任务
- 请求模型：TaskListRequest (task_type?: str, status?: str, limit?: int, offset?: int)
- 响应模型：List[TaskResponse]
- 备注：limit 默认 50，最大 100；按 created_at 降序

## GET /pending
- 方法：GET
- 路由：/pending
- 描述：获取当前用户所有状态为 'pending' 的任务
- 鉴权：需要登录
- 响应模型：List[PendingTaskResponse]

## POST / (创建任务)
- 方法：POST
- 路由：/
- 描述：创建新的任务记录（TaskCreateRequest），验证 conversation 所属
- 鉴权：需要登录
- 请求模型：TaskCreateRequest
- 响应模型：TaskCreateResponse

## POST /execute
- 方法：POST
- 路由：/execute
- 描述：执行任务，返回流式 SSE（StreamingResponse）用于实时返回执行进度/结果
- 鉴权：需要登录
- 请求模型：TaskExecuteRequest
- 响应：SSE 流（不同 task_type 路由到 geometry/retrieval/optimize 等生成器）
- 备注：该接口内部会验证任务归属并在 Redis 中管理消息历史

## POST /optimize/submit-params
- 方法：POST
- 路由：/optimize/submit-params
- 描述：提交优化参数并保存到任务对应模型目录
- 鉴权：需要登录
- 请求模型：OptimizationParamsRequest
- 响应：{"message": "Parameters received successfully and printed to console."}

## GET /optimize/progress/{task_id}
- 方法：GET
- 路由：/optimize/progress/{task_id}
- 描述：订阅优化任务的进度 SSE（从 Redis / Celery pubsub 或队列读取）
- 鉴权：公开（未显式 require 登录）
- 响应：StreamingResponse (SSE)

## GET /optimize/queue_length
- 方法：GET
- 路由：/optimize/queue_length
- 描述：返回当前优化队列长度和运行中的数量
- 鉴权：公开
- 响应：{"length": int, "running": int}

---

注意：SSE 流接口对前端有特殊要求（保持连接、监听事件类型如 text_chunk、image_chunk、message_end 等）。