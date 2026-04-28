# 后端 ToDo（来自前端修改意见整理）

更新时间：2026-03-18  
适用项目：`cautod_fastapi`（FastAPI + SSE + Redis + Celery）

## 背景与现状对齐（便于评审/排期）

- **现有 SSE 执行入口**：`POST /api/tasks/execute`（`apps/routes/tasks.py`），按 `task_type` 路由到 `geometry/retrieval/optimize` 的流式生成器。
- **现有任务取消接口（已具备雏形）**：`POST /api/tasks/cancel/{task_id}`（`apps/routes/tasks.py`）
  - **流式任务**：通过 Redis 终止标志（`apps.task_utils.set_task_terminated`）协同生成器退出。
  - **优化任务**：队列移除 + `celery.control.revoke(..., terminate=True)` + Redis pub/sub 通知。
- **已知缺口**：
  - SSE 连接断开时，后端目前**不保证**自动取消/释放计算资源（尤其是 LLM/算法侧仍可能继续跑）。
  - 前端任务历史状态目前依赖轮询；后端缺少**全局状态推送**（SSE/WebSocket）以替代轮询。
  - 并发/状态机/消息原子性仍有强化空间（避免“跨会话串流/状态覆盖”）。
  - 断点续传/意外恢复：缺少统一的 checkpoint 持久化与恢复语义。

---

## P0：深度任务调度——真正的“任务终止与资源释放”（🌟🌟🌟🌟🌟）

### P0-1 客户端断开检测（SSE disconnect -> Cancellation Token）

- **目标**：当 SSE 客户端断开（离开页面、刷新、网络断开、abort）时，后端能尽快感知并触发任务取消，避免 GPU/CPU 空转。
- **实现要点**：
  - 在所有 SSE generator 的 `while/async for` 循环内，周期性检查：
    - `await request.is_disconnected()`（FastAPI/Starlette Request）
    - 捕获 `asyncio.CancelledError` / `BrokenPipeError` / `ClientDisconnect`（依赖具体栈）
  - 一旦断开：
    - 写入 Redis 终止标志：`task_terminate:{task_id}`
    - 尝试调用底层“可取消”的外部调用：
      - LLM：显式关闭上游 streaming client / session（若 SDK 支持 cancel/close）
      - 算法：发送 kill/terminate 指令或进程中断（若为子进程，需记录 PID/JobId）
    - 任务状态落库：`running/queued -> cancelled`（或 `aborted`，需统一枚举）
    - 推送终止事件（用于前端即时 UI 收敛）：见 P1 状态流
- **建议改造点**：
  - 将 `request: Request` 透传进 `geometry_stream_generator` / `retrieval_stream_generator` / `optimize_stream_generator`
  - 抽象统一的 `CancellationContext`：
    - `task_id, conversation_id, user_id`
    - `is_cancelled(): bool`（检查 Redis + disconnect）
    - `cancel(reason)`（写 Redis、更新 DB、推送事件、释放外部资源）
- **验收标准**：
  - 前端 abort SSE 后，后端在 $< 1s \sim 3s$ 内停止继续生成 chunk；
  - GPU/算法侧调用链停止（通过日志、监控指标或任务耗时显著下降验证）；
  - DB 中该任务状态变为 `cancelled`，且后端不会继续写入该任务的消息/结果。

### P0-2 主动终止接口标准化（/api/tasks/{taskId}/cancel）

- **目标**：前端点击“新建任务/删除任务/离开页面”时主动调用后端取消，后端强制释放资源。
- **现状**：已有 `POST /api/tasks/cancel/{task_id}`，但需要**路径与语义**对齐前端约定。
- **ToDo**：
  - **接口规范对齐**：
    - 推荐新增并兼容旧接口（避免前端/历史客户端断裂）：
      - `POST /api/tasks/{task_id}/cancel`（新）
      - 保留 `POST /api/tasks/cancel/{task_id}`（旧，标记 deprecated）
  - **取消语义增强**：
    - 支持 `reason`（`user_action/new_task/page_leave/timeout/admin`）
    - 支持 `mode`（`graceful`/`force`）
  - **幂等性**：重复 cancel 返回一致结果（200/202），避免前端重试导致 500
  - **审计日志**：记录取消人、原因、耗时、是否成功释放（用于排查资源泄漏）
- **验收标准**：
  - 任意任务多次调用 cancel 不会报错；
  - optimize（Celery）与 geometry/retrieval（SSE）均能在可接受时间内停止；
  - 任务状态与事件通知一致（见 P1）。

### P0 当前实现说明（2026-04-01）

- **新旧路由**：
  - 新：`POST /api/tasks/{task_id}/cancel`
  - 旧（兼容，deprecated）：`POST /api/tasks/cancel/{task_id}`
  - 两者复用同一业务取消入口，均支持幂等取消。
- **取消语义**：
  - `reason ∈ {user_action,new_task,page_leave,timeout,admin}`
  - `mode ∈ {graceful,force}`
  - 取消后统一状态：`cancelled`（兼容读取历史 `canceled`）。
- **断开自动取消**：
  - SSE 流内检测 `request.is_disconnected()`。
  - 捕获 `asyncio.CancelledError` / `BrokenPipeError` / `ClientDisconnect` 后统一执行取消逻辑。
- **取消审计日志字段**：
  - `task_id`, `user_id`, `reason`, `mode`, `elapsed_ms`, `release_result(success/partial/failed)`, `already_cancelled`, `status_before`, `status_after`, `errors`。
- **已知限制**：
  - 当前 `force` 语义已打通接口和审计，但底层外部服务（如特定 LLM SDK 或算法进程）是否支持硬中断仍依赖具体 SDK/服务端能力。
  - Celery revoke 优先使用 `task_id -> celery_task_id` 映射，若映射缺失会回退到业务 task_id 尝试 revoke。

---

## P1：状态同步升级——用 SSE/WebSocket 替代轮询（🌟🌟🌟🌟）

### P1-1 全局状态推送通道：`/api/tasks/status-stream`（SSE）或 WebSocket

- **目标**：后端在任务状态变化时主动 push，前端移除 `setInterval` 轮询。
- **方案建议（优先 SSE，成本更低）**：
  - 新增：`GET /api/tasks/status-stream`
  - **推送内容**：任务状态更新事件 JSON（最小必要字段）
  - **实现方式**：
    - 任务状态变更点统一发事件（DB 更新后 publish）
    - 事件总线：
      - 简单实现：Redis pub/sub `task_status_events:{user_id}`（按用户隔离）
      - 进阶实现：Redis Streams（可回放，利于断点恢复）
- **验收标准**：
  - 前端在多任务并行下，轮询请求数显著下降（接近 0）；
  - 状态变化 UI 延迟 < 1s（网络正常）；
  - 断线重连后能继续收到后续状态更新。

### P1-2 事件驱动：状态变化的统一触发点

- **ToDo**：
  - 抽一个 `TaskStatusService.update_status(task_id, status, payload?)`：
    - 更新 DB
    - publish 状态事件到 Redis（用户级/工作区级 channel）
  - 将散落的 `task.status = ...; await task.save()` 逐步替换为服务调用

---

## P1：数据层校验与隔离——增强任务“防串行/防串流”（🌟🌟🌟🌟）

### P1-3 严格状态机与并发控制（create/execute 阶段）

- **目标**：同一 user/workspace 下，避免“同类型冲突任务”抢资源卡死；给出明确反馈或排队信息。
- **ToDo**：
  - 定义任务状态机（枚举 + allowed transitions）
  - `create/execute` 时做并发校验（`user_id + task_type` 维度）
  - optimize 队列 key 统一（当前存在 `optimize_queue` 与 `optimize` 混用风险，需要梳理）
- **验收标准**：
  - 并发提交同类型任务有确定行为（拒绝或排队），不会出现状态覆盖/互相抢占导致卡死；
  - 返回信息足够前端提示（“已有任务运行中/你在队列第 N 位”）。

### P1-4 消息原子性关联：chunk/最终结果强绑定 taskId + conversationId

- **目标**：杜绝历史消息混入其他会话/任务；前端可做强校验。
- **ToDo**：
  - 所有 SSE 事件统一 schema（即使是文本 chunk）也必须包含 `task_id + conversation_id + seq`
  - Redis/DB 写入时做一致性校验（不匹配则拒绝写入）
- **验收标准**：
  - 任意并发/切换页面场景下，不会出现跨会话串流；
  - 前端可通过 `task_id+conversation_id` 校验丢弃异常事件。

---

## P2：健壮的断点续传/意外恢复（🌟🌟🌟）

### P2-1 中间态持久化（Checkpoint）

- **目标**：网络抖动/刷新/浏览器关闭后，前端能通过历史接口看到“中断前进度”，避免长期卡在 in_progress。
- **ToDo**：
  - 定义 checkpoint 数据结构（DB 或 Redis Streams）
  - checkpoint 写入点：每 N 个 chunk（节流）+ 状态跃迁点
  - 历史接口返回最新 checkpoint 与最后一次事件时间
- **验收标准**：
  - 刷新页面后，前端能看到该任务上次 checkpoint 的阶段与部分内容；
  - 对已取消/失败任务，不会继续显示“处理中”。

---

## 附：建议的落点文件（便于分工）

- `apps/routes/tasks.py`：`/status-stream`、cancel 路由兼容、SSE disconnect 处理
- `apps/task_utils.py`：终止标志/幂等/原因/force 模式
- `apps/geometry.py` / `apps/retrieval.py` / `apps/optimize.py`：生成器内 cancel 检查 + 资源释放
- `apps/celery_tasks.py`：revoke/terminate 的真实 celery task id 映射梳理
- `database/models.py`：状态机/状态历史/checkpoint（如决定落 DB）

---

## 与前端约定的最小事件格式（建议）

```json
{
  "event": "task_status",
  "task_id": "123",
  "conversation_id": "c_456",
  "task_type": "geometry",
  "status": "running",
  "updated_at": "2026-03-18T10:00:00Z",
  "seq": 42,
  "payload": {
    "queue_position": 2,
    "progress": 35,
    "message": "正在生成..."
  }
}
```


