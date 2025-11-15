# apps.retrieval 模块 API 文档

路由前缀：无独立路由（此模块未通过 include_router 注册到 FastAPI），通常被 tasks.execute 调用，实际 URL 前缀由 `/api/tasks`。

说明：该模块主要包含辅助的检索流生成器，并未注册独立的路由。

- 提供函数：retrieval_stream_generator(request, current_user, redis_client, combinde_query, task)
- 用途：用于在 tasks.execute 中处理 task_type == "retrieval" 的 SSE 流返回
- 鉴权：由调用方（tasks.execute）负责检查

---

备注：此文件未导出 APIRouter，因此没有独立的 HTTP 路由。