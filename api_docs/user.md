# apps.user 模块 API 文档

路由前缀：`/api/user`  （来自 main.py 中 app.include_router(user, prefix="/api/user")）

说明：此文档按路由路径列出 `apps/user.py` 中公开的接口，包含方法、路径、简要说明、鉴权与请求/响应模型信息。

## GET /me
- 方法：GET
- 路由：/me
- 描述：获取当前用户信息（从 token 读取用户并返回数据库中最新信息）
- 鉴权：需要登录（依赖 get_current_active_user）
- 请求：无
- 响应模型：UserResponse（包含 user_id、email、created_at、username、role）
- 备注：返回 role 字段（user、premium、admin）

## GET /login
- 方法：GET
- 路由：/login
- 描述：简易登录页面占位（返回 JSON）。
- 鉴权：公开

## POST /login
- 方法：POST
- 路由：/login
- 描述：表单登录，接收 email 和 password（Form）并返回 JWT
- 鉴权：公开
- 请求：Form(email, password)
- 响应：{"status":"success", "access_token": "..."}

## GET /auth/github
- 方法：GET
- 路由：/auth/github
- 描述：返回 GitHub 授权 URL（OAuth2 重定向）
- 鉴权：公开

## GET /auth/github/callback
- 方法：GET
- 路由：/auth/github/callback?code=...
- 描述：处理 GitHub 回调，交换令牌并返回 GitHub 用户信息
- 鉴权：公开

## GET /auth/google
- 方法：GET
- 路由：/auth/google
- 描述：返回 Google 授权 URL（OAuth2）
- 鉴权：公开

## GET /auth/google/callback
- 方法：GET
- 路由：/auth/google/callback?code=...
- 描述：处理 Google 回调并获取用户信息
- 鉴权：公开

## GET /register
- 方法：GET
- 路由：/register
- 描述：注册页面占位
- 鉴权：公开

## POST /register
- 方法：POST
- 路由：/register
- 描述：用户注册（接收 username, email, pwd 表单），创建 Users 记录
- 鉴权：公开
- 请求：Form(username, email, pwd)
- 响应：{"status":"success", "user_id": ..., "email": ...}
- 备注：返回类型标注为 UserResponse，但实际返回自定义 JSON 包含 status & user_id

## GET /{user_id}
- 方法：GET
- 路由：/{user_id}
- 描述：通过用户 ID 获取指定用户信息
- 鉴权：公开（没有当前用户检查）
- 响应模型：UserResponse

## PUT /update-role
- 方法：PUT
- 路由：/update-role
- 描述：管理员更新指定用户的角色
- 鉴权：需要登录，且当前用户必须为管理员（代码内检查 admin_user.role == UserRole.ADMIN）
- 请求模型：UserRoleUpdateRequest（user_id, role）
- 响应：{"status":"success", "message":"...", "user_id":..., "new_role":...}

---

备注：role 值使用枚举 UserRole（user / premium / admin）。请确保数据库已应用 `role` 字段的迁移。