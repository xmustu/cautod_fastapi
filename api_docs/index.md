# API 文档目录（总览）

说明：本文件是 `api_docs/` 下的总入口目录，列出各个子模块、它们在 `main.py` 中注册的路由前缀、简要说明，以及对应的 Markdown 文档路径，方便开发者快速定位接口详情。

> 文档位置：.\CAutoD\cautod_fastapi\api_docs

---

## 模块列表

- 登录认证模块 ⭐ 新增
  - 路由前缀：`/api/auth`
  - 简介：OAuth2 token 登录、密码重置、邮箱验证等认证功能。
  - 文档文件：`login.md`
  - 完整示例 URL：`/api/auth/login/access-token`、`/api/auth/password-recovery`、`/api/auth/verify-email`

- 用户模块
  - 路由前缀：`/api/user`
  - 简介：用户注册、登录、OAuth 回调、获取当前用户信息、管理员可更新角色等。
  - 文档文件：`user.md`
  - 完整示例 URL：`/api/user/me`、`/api/user/register`、`/api/user/update-role`

- 几何建模模块
  - 路由前缀：`/api/geometry`
  - 简介：创建会话、与 Dify 集成的几何建模流（SSE）生成器等。
  - 文档文件：`geometry.md`
  - 完整示例 URL：`/api/geometry/conversation`

- 设计优化模块
  - 路由前缀：`/api/optimize`
  - 简介：与外部算法服务交互的优化接口、AlgorithmClient、SSE 流；需要 Authorization header 验证。 
  - 文档文件：`optimize.md`
  - 完整示例 URL：`/api/optimize/`、`/api/optimize/progress/{task_id}`

- 任务管理模块
  - 路由前缀：`/api/tasks`
  - 简介：任务创建、执行（SSE）、任务列表查询（管理员可查看所有）、优化参数提交等。
  - 文档文件：`tasks.md`
  - 完整示例 URL：`/api/tasks/list`、`/api/tasks/execute`

- 管理员模块 ⭐ 新增
  - 路由前缀：`/api/admin`
  - 简介：系统统计概览（包含 CPU、内存、GPU 监控）、用户管理（CRUD）、任务管理、系统配置等管理员功能。
  - 文档文件：`admin.md`
  - 完整示例 URL：`/api/admin/stats/overview`、`/api/admin/users`、`/api/admin/tasks`
  - 权限要求：所有接口都需要管理员角色

- 功能/文件与会话管理模块
  - 路由前缀：`/api`
  - 简介：文件上传/下载、获取模型文件、会话获取/删除、任务状态查询等。
  - 文档文件：`router.md`
  - 完整示例 URL：`/api/download_file`、`/api/conversation/{conversation_id}`

- 对话管理模块
  - 路由前缀：`/api/chat`
  - 简介：SSE 对话流、从 Redis 读取/清除会话历史、获取用户历史记录等。
  - 文档文件：`chat.md`
  - 完整示例 URL：`/api/chat/stream`、`/api/chat/history`

- 检索辅助模块（无独立路由）
  - 路由前缀：无（未单独 include_router）
  - 简介：包含 `retrieval_stream_generator` 等辅助函数，通常由 `/api/tasks` 下的执行接口调用。
  - 文档文件：`retrieval.md`

---

## 使用说明

- 打开 `.\CAutoD\cautod_fastapi\api_docs`，进入对应模块的 `.md` 文件查看详细接口信息、请求/响应模型与示例说明。
- 完整 URL = `路由前缀` + `文档中列出的 endpoint path`。
  - 例如：用户信息接口在 `user.md` 中列为 `/me`，结合前缀拼接为 `/api/user/me`。

## 建议的下一步（可选）

- 为每个 endpoint 添加自动生成的示例请求/响应（基于 Pydantic schema）；我可以自动生成并追加到每个子文档中。
- 把这些 Markdown 转为 HTML（例如 MkDocs）并部署为可浏览的文档站点。
- 将 `api_docs/` 加入版本控制并提交（我可以生成建议的 commit 消息）。

---
