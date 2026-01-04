# apps.routes.admin 模块 API 文档

路由前缀：`/api/admin`  （来自 main.py 中 app.include_router(admin_router, prefix="/api")，admin_router 本身有 prefix="/admin"）

说明：此文档列出管理员相关的 API 接口，所有接口都需要管理员权限（通过 `require_admin` 依赖验证）。

## 权限要求

所有管理员接口都需要：
- 用户已登录（有效的 JWT Token）
- 用户角色为 `admin`

在请求头中需要包含：
```
Authorization: Bearer <access_token>
```

---

## 系统统计相关路由

### GET /stats/overview

- **方法**：GET
- **路由**：`/api/admin/stats/overview`
- **描述**：获取系统整体统计数据，包括用户、任务、会话数量，以及系统资源使用情况（CPU、内存、GPU）
- **鉴权**：需要管理员权限
- **请求**：无
- **响应模型**：`SystemStats`

#### 响应字段说明

```json
{
  "total_users": 0,              // 总用户数
  "total_tasks": 0,              // 总任务数
  "total_conversations": 0,      // 总会话数
  "active_tasks": 0,             // 运行中的任务数
  "completed_tasks": 0,          // 已完成的任务数
  "failed_tasks": 0,             // 失败的任务数
  "pending_tasks": 0,            // 待处理的任务数
  "users_today": 0,              // 今日新增用户数
  "tasks_today": 0,              // 今日新增任务数
  "cpu_usage": 45.5,             // CPU 使用率 (%)
  "cpu_cores": 8,                // CPU 核心数
  "memory_usage": 62.3,          // 内存使用率 (%)
  "memory_total": 16384,         // 总内存 (MB)
  "memory_used": 10240,          // 已用内存 (MB)
  "memory_available": 6144,      // 可用内存 (MB)
  "gpu_usage": 30.0,             // GPU 使用率 (%)
  "gpu_memory_used": 2048,       // GPU 显存已用 (MB)
  "gpu_memory_total": 8192,      // GPU 显存总量 (MB)
  "gpu_count": 1                 // GPU 数量
}
```

**注意**：
- 系统资源相关字段（cpu_usage, memory_usage, gpu_usage 等）可能为 `null`，如果系统监控库（psutil/pynvml）不可用或获取失败
- CPU 使用率需要短暂采样时间（0.1秒），可能略有延迟

---

### GET /stats/users

- **方法**：GET
- **路由**：`/api/admin/stats/users`
- **描述**：获取用户统计数据列表，按创建时间降序排列
- **鉴权**：需要管理员权限
- **请求参数**：
  - `limit` (Query, 可选): 返回数量限制，默认 10，范围 1-100
- **响应模型**：`List[UserStatsItem]`

#### 响应字段说明

```json
[
  {
    "user_id": 1,
    "username": "user1",
    "email": "user1@example.com",
    "role": "user",
    "task_count": 5,
    "conversation_count": 3,
    "created_at": "2024-01-01T00:00:00"
  }
]
```

---

### GET /stats/tasks/types

- **方法**：GET
- **路由**：`/api/admin/stats/tasks/types`
- **描述**：获取各类型任务的数量统计
- **鉴权**：需要管理员权限
- **请求**：无
- **响应模型**：`List[TaskTypeStats]`

#### 响应字段说明

```json
[
  {
    "task_type": "geometry",
    "count": 10
  },
  {
    "task_type": "optimize",
    "count": 5
  }
]
```

---

### GET /stats/daily

- **方法**：GET
- **路由**：`/api/admin/stats/daily`
- **描述**：获取最近N天的统计数据，按日期升序排列
- **鉴权**：需要管理员权限
- **请求参数**：
  - `days` (Query, 可选): 查询天数，默认 7，范围 1-30
- **响应模型**：`List[DailyStats]`

#### 响应字段说明

```json
[
  {
    "date": "2024-01-01",
    "user_count": 2,
    "task_count": 5,
    "conversation_count": 3
  },
  {
    "date": "2024-01-02",
    "user_count": 1,
    "task_count": 3,
    "conversation_count": 2
  }
]
```

---

## 用户管理相关路由

### GET /users

- **方法**：GET
- **路由**：`/api/admin/users`
- **描述**：获取用户列表，支持分页、搜索、筛选
- **鉴权**：需要管理员权限
- **请求参数**：
  - `page` (Query, 可选): 页码，从 1 开始，默认 1
  - `page_size` (Query, 可选): 每页数量，默认 20，范围 1-100
  - `search` (Query, 可选): 搜索关键词，会匹配用户名或邮箱
  - `role` (Query, 可选): 角色筛选，可选值：`user`、`premium`、`admin`
- **响应模型**：`PaginatedResponse`

#### 响应字段说明

```json
{
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5,
  "items": [
    {
      "user_id": 1,
      "username": "user1",
      "email": "user1@example.com",
      "role": "user",
      "created_at": "2024-01-01T00:00:00"
    }
  ]
}
```

---

### GET /users/{user_id}

- **方法**：GET
- **路由**：`/api/admin/users/{user_id}`
- **描述**：获取指定用户的详细信息
- **鉴权**：需要管理员权限
- **路径参数**：
  - `user_id` (int): 用户 ID
- **响应模型**：`AdminUserDetail`

#### 响应字段说明

```json
{
  "user_id": 1,
  "username": "user1",
  "email": "user1@example.com",
  "role": "user",
  "created_at": "2024-01-01T00:00:00",
  "task_count": 5,
  "conversation_count": 3
}
```

#### 错误响应

- `404`: 用户不存在

---

### POST /users

- **方法**：POST
- **路由**：`/api/admin/users`
- **描述**：管理员创建新用户
- **鉴权**：需要管理员权限
- **请求模型**：`AdminUserCreate`

#### 请求字段说明

```json
{
  "username": "newuser",           // 必填，最大长度 255
  "email": "newuser@example.com",  // 必填，有效邮箱格式
  "password": "password123",       // 必填，最小长度 6
  "role": "user"                   // 可选，默认 "user"，可选值：user/premium/admin
}
```

- **响应模型**：`AdminResponse`

#### 响应字段说明

```json
{
  "status": "success",
  "message": "用户创建成功",
  "data": {
    "user_id": 1
  }
}
```

#### 错误响应

- `400`: 邮箱已被注册

---

### PUT /users/{user_id}

- **方法**：PUT
- **路由**：`/api/admin/users/{user_id}`
- **描述**：管理员更新用户信息
- **鉴权**：需要管理员权限
- **路径参数**：
  - `user_id` (int): 用户 ID
- **请求模型**：`AdminUserUpdate`

#### 请求字段说明

```json
{
  "username": "updatedname",        // 可选
  "email": "newemail@example.com",  // 可选
  "role": "premium"                 // 可选，可选值：user/premium/admin
}
```

- **响应模型**：`AdminResponse`

#### 响应字段说明

```json
{
  "status": "success",
  "message": "用户信息更新成功"
}
```

#### 错误响应

- `404`: 用户不存在
- `400`: 邮箱已被使用

---

### DELETE /users/{user_id}

- **方法**：DELETE
- **路由**：`/api/admin/users/{user_id}`
- **描述**：管理员删除用户（同时删除该用户的所有任务和会话）
- **鉴权**：需要管理员权限
- **路径参数**：
  - `user_id` (int): 用户 ID
- **响应模型**：`AdminResponse`

#### 响应字段说明

```json
{
  "status": "success",
  "message": "用户删除成功"
}
```

#### 错误响应

- `404`: 用户不存在
- `400`: 不能删除自己

---

### POST /users/batch-delete

- **方法**：POST
- **路由**：`/api/admin/users/batch-delete`
- **描述**：批量删除用户（同时删除相关任务和会话）
- **鉴权**：需要管理员权限
- **请求模型**：`AdminBatchDeleteUsers`

#### 请求字段说明

```json
{
  "user_ids": [1, 2, 3]  // 必填，至少包含一个用户 ID
}
```

- **响应模型**：`AdminResponse`

#### 响应字段说明

```json
{
  "status": "success",
  "message": "成功删除 3 个用户"
}
```

#### 错误响应

- `400`: 没有可删除的用户（所有 ID 都被过滤掉，例如包含自己的 ID）

**注意**：
- 批量删除会自动过滤掉当前管理员自己的 ID，防止误删
- 只有成功删除的用户才会被计数

---

## 任务管理相关路由

### GET /tasks

- **方法**：GET
- **路由**：`/api/admin/tasks`
- **描述**：获取任务列表，支持分页、筛选
- **鉴权**：需要管理员权限
- **请求参数**：
  - `page` (Query, 可选): 页码，从 1 开始，默认 1
  - `page_size` (Query, 可选): 每页数量，默认 20，范围 1-100
  - `task_type` (Query, 可选): 任务类型筛选
  - `status` (Query, 可选): 任务状态筛选，可选值：`pending`、`running`、`completed`、`failed`
  - `user_id` (Query, 可选): 用户 ID 筛选
- **响应模型**：`PaginatedResponse`

#### 响应字段说明

```json
{
  "total": 50,
  "page": 1,
  "page_size": 20,
  "total_pages": 3,
  "items": [
    {
      "task_id": 1,
      "user_id": 1,
      "username": "user1",
      "task_type": "geometry",
      "status": "completed",
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T01:00:00"
    }
  ]
}
```

---

### GET /tasks/{task_id}

- **方法**：GET
- **路由**：`/api/admin/tasks/{task_id}`
- **描述**：获取指定任务的详细信息，包括任务结果和错误日志
- **鉴权**：需要管理员权限
- **路径参数**：
  - `task_id` (int): 任务 ID
- **响应模型**：`AdminTaskDetail`

#### 响应字段说明

```json
{
  "task_id": 1,
  "user_id": 1,
  "username": "user1",
  "conversation_id": "conv_123",
  "dify_conversation_id": "dify_456",
  "task_type": "geometry",
  "status": "completed",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T01:00:00",
  "geometry_result": {
    "geometry_id": 1,
    "cad_file_path": "/path/to/cad/file",
    "code_file_path": "/path/to/code/file",
    "preview_image_path": "/path/to/image",
    "created_at": "2024-01-01T01:00:00"
  },
  "optimization_result": null,
  "error_logs": null
}
```

**注意**：
- `geometry_result` 仅在 `task_type` 为 `"geometry"` 时存在
- `optimization_result` 仅在 `task_type` 为 `"optimize"` 时存在
- `error_logs` 为数组，包含错误信息和时间戳

#### 错误响应

- `404`: 任务不存在

---

### PUT /tasks/{task_id}

- **方法**：PUT
- **路由**：`/api/admin/tasks/{task_id}`
- **描述**：管理员更新任务状态
- **鉴权**：需要管理员权限
- **路径参数**：
  - `task_id` (int): 任务 ID
- **请求模型**：`AdminTaskUpdate`

#### 请求字段说明

```json
{
  "status": "completed"  // 可选，可选值：pending/running/completed/failed
}
```

- **响应模型**：`AdminResponse`

#### 响应字段说明

```json
{
  "status": "success",
  "message": "任务状态更新成功"
}
```

#### 错误响应

- `404`: 任务不存在

---

### DELETE /tasks/{task_id}

- **方法**：DELETE
- **路由**：`/api/admin/tasks/{task_id}`
- **描述**：管理员删除任务（同时删除相关的几何结果、优化结果和错误日志）
- **鉴权**：需要管理员权限
- **路径参数**：
  - `task_id` (int): 任务 ID
- **响应模型**：`AdminResponse`

#### 响应字段说明

```json
{
  "status": "success",
  "message": "任务删除成功"
}
```

#### 错误响应

- `404`: 任务不存在

---

### POST /tasks/batch-delete

- **方法**：POST
- **路由**：`/api/admin/tasks/batch-delete`
- **描述**：批量删除任务（同时删除相关结果和错误日志）
- **鉴权**：需要管理员权限
- **请求模型**：`AdminBatchDeleteTasks`

#### 请求字段说明

```json
{
  "task_ids": [1, 2, 3]  // 必填，至少包含一个任务 ID
}
```

- **响应模型**：`AdminResponse`

#### 响应字段说明

```json
{
  "status": "success",
  "message": "成功删除 3 个任务"
}
```

---

## 系统配置相关路由

### GET /config

- **方法**：GET
- **路由**：`/api/admin/config`
- **描述**：获取系统配置（当前为默认值，后续可从数据库或配置文件读取）
- **鉴权**：需要管理员权限
- **请求**：无
- **响应模型**：`SystemConfig`

#### 响应字段说明

```json
{
  "max_tasks_per_user": 100,
  "max_conversations_per_user": 50,
  "enable_registration": true,
  "enable_email_verification": false,
  "maintenance_mode": false
}
```

---

### PUT /config

- **方法**：PUT
- **路由**：`/api/admin/config`
- **描述**：更新系统配置（当前仅返回成功响应，后续可实现持久化到数据库或配置文件）
- **鉴权**：需要管理员权限
- **请求模型**：`SystemConfig`

#### 请求字段说明

```json
{
  "max_tasks_per_user": 100,           // 可选，每个用户最大任务数
  "max_conversations_per_user": 50,    // 可选，每个用户最大会话数
  "enable_registration": true,         // 可选，是否启用注册
  "enable_email_verification": false,  // 可选，是否启用邮箱验证
  "maintenance_mode": false            // 可选，是否维护模式
}
```

- **响应模型**：`AdminResponse`

#### 响应字段说明

```json
{
  "status": "success",
  "message": "系统配置更新成功"
}
```

**注意**：
- 当前配置更新不会持久化，重启后恢复默认值
- 后续版本可能会实现配置持久化功能

---

## 使用示例

### 获取系统统计概览

```bash
curl -X GET "http://localhost:8081/api/admin/stats/overview" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 获取用户列表（带搜索）

```bash
curl -X GET "http://localhost:8081/api/admin/users?page=1&page_size=20&search=test" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 创建新用户

```bash
curl -X POST "http://localhost:8081/api/admin/users" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newuser",
    "email": "newuser@example.com",
    "password": "password123",
    "role": "user"
  }'
```

### 批量删除用户

```bash
curl -X POST "http://localhost:8081/api/admin/users/batch-delete" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_ids": [1, 2, 3]
  }'
```

---

## 备注

1. **权限验证**：所有接口都通过 `require_admin` 依赖进行权限验证，只有管理员角色的用户才能访问。

2. **系统资源监控**：
   - CPU 和内存监控依赖 `psutil` 库
   - GPU 监控依赖 `pynvml` 库（仅支持 NVIDIA GPU）
   - 如果库不可用或获取失败，相关字段会返回 `null`

3. **分页说明**：
   - 所有列表接口都支持分页
   - 页码从 1 开始
   - `total_pages` 为总页数（向上取整）

4. **批量操作**：
   - 批量删除操作会自动跳过不存在的记录
   - 返回消息中包含实际删除的数量

5. **错误处理**：
   - 所有接口都包含适当的错误处理
   - 返回标准的 HTTP 状态码（400, 404, 403 等）
   - 错误信息在响应体中返回

