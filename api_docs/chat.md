# apps.chat 模块 API 文档

路由前缀：`/api/chat`  （来自 main.py 中 app.include_router(chat_router, prefix="/api/chat")）

说明：对话（聊天）管理相关接口与 Redis 消息历史管理。

## GET /
- 方法：GET
- 路由：/
- 描述：对话管理首页
- 鉴权：公开

## POST /stream

### 基本信息
- **方法**：POST
- **路由**：`/stream`
- **描述**：流式对话生成接口，返回 SSE (Server-Sent Events) 流式响应
- **鉴权**：需要登录（通过 `check_maintenance_mode` 验证）
- **响应**：StreamingResponse (text/event-stream)
- **备注**：内部实现会调用 `save_or_update_message_in_redis` 存储消息并发送事件：conversation_info, text_chunk, part_chunk, image_chunk, message_end 等

### 请求参数

**请求头**：
| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| Authorization | string | header | 是 | Bearer token，格式：`Bearer {access_token}` |
| Content-Type | string | header | 是 | 应为 `application/json` |

**请求体**（通过中间件设置，具体格式需根据实际实现）：
- 此端点通过 `Request` 对象获取参数，需要从请求体中解析以下字段：
  - `user_id` (string): 用户ID
  - `task_id` (string): 任务ID
  - `user_messages` (array): 用户消息列表

### 响应格式

返回 SSE (Server-Sent Events) 流式响应，媒体类型为 `text/event-stream`。

响应头：
- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `Access-Control-Allow-Origin: *`

### 请求示例

```bash
curl -X POST "http://localhost:8081/api/chat/stream" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "task_id": "task_456",
    "user_messages": [...]
  }'
```

### 注意事项

- 此接口返回流式响应，需要使用支持 SSE 的客户端接收
- 消息会实时保存到 Redis 中
- 响应中包含多种事件类型，客户端需要根据事件类型进行相应处理

## GET /task

### 基本信息
- **方法**：GET
- **路由**：`/task`
- **描述**：获取指定任务的对话历史记录（支持分页，兼容不分页请求）
- **鉴权**：需要登录（通过 `check_maintenance_mode` 验证）
- **响应模型**：`PaginatedResponse`
- **兼容性**：不传分页参数时返回全部数据，保持与旧版本兼容

### 请求参数

**请求头**：
| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| Authorization | string | header | 是 | Bearer token，格式：`Bearer {access_token}` |

**查询参数**：
| 参数名 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|--------|------|------|------|--------|------|
| task_id | string | query | 是 | - | 任务ID |
| page | integer | query | 否 | None | 页码，从 1 开始，最小值为 1。**不传则返回全部数据（兼容旧逻辑）** |
| page_size | integer | query | 否 | None | 每页数量，范围：1-100。**不传则返回全部数据（兼容旧逻辑）** |

### 响应格式

响应体为 `PaginatedResponse` 格式：

```json
{
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5,
  "items": [
    {
      "role": "user",
      "content": "用户消息内容",
      "timestamp": 1234567890.123
    },
    {
      "role": "assistant",
      "content": "助手回复内容",
      "timestamp": 1234567891.456
    }
  ]
}
```

**响应字段说明**：
- `total` (integer): 总记录数
- `page` (integer): 当前页码
- `page_size` (integer): 每页数量
- `total_pages` (integer): 总页数（向上取整）
- `items` (array): 当前页的消息列表，每个消息包含：
  - `role` (string): 消息角色（"user" 或 "assistant"）
  - `content` (string): 消息内容
  - `timestamp` (float): 消息时间戳

### 请求示例

```bash
# 获取所有数据（不传分页参数，兼容旧逻辑）
curl -X GET "http://localhost:8081/api/chat/task?task_id=task_123" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 获取第一页，每页 20 条（分页模式）
curl -X GET "http://localhost:8081/api/chat/task?task_id=task_123&page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 获取第二页，每页 10 条
curl -X GET "http://localhost:8081/api/chat/task?task_id=task_123&page=2&page_size=10" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 错误响应

- **500 Internal Server Error**: 获取聊天历史失败
  ```json
  {
    "detail": "获取聊天历史失败"
  }
  ```

---

## GET /history

### 基本信息
- **方法**：GET
- **路由**：`/history`
- **描述**：获取当前用户的所有对话历史记录（支持分页，兼容不分页请求）
- **鉴权**：需要登录（通过 `check_maintenance_mode` 验证）
- **响应模型**：`PaginatedResponse`
- **兼容性**：不传分页参数时返回全部数据，保持与旧版本兼容

### 请求参数

**请求头**：
| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| Authorization | string | header | 是 | Bearer token，格式：`Bearer {access_token}` |

**查询参数**：
| 参数名 | 类型 | 位置 | 必填 | 默认值 | 说明 |
|--------|------|------|------|--------|------|
| page | integer | query | 否 | None | 页码，从 1 开始，最小值为 1。**不传则返回全部数据（兼容旧逻辑）** |
| page_size | integer | query | 否 | None | 每页数量，范围：1-100。**不传则返回全部数据（兼容旧逻辑）** |

### 响应格式

响应体为 `PaginatedResponse` 格式：

```json
{
  "total": 50,
  "page": 1,
  "page_size": 20,
  "total_pages": 3,
  "items": [
    {
      "task_id": "task_123",
      "conversation_id": "conv_456",
      "task_type": "几何建模",
      "last_message": "最后一条消息内容",
      "last_timestamp": 1234567890.123,
      "last_time": "2024-01-01 12:00:00"
    },
    {
      "task_id": "task_124",
      "conversation_id": "conv_457",
      "task_type": "设计优化",
      "last_message": "另一条消息内容",
      "last_timestamp": 1234567880.456,
      "last_time": "2024-01-01 11:59:40"
    }
  ]
}
```

**响应字段说明**：
- `total` (integer): 总记录数
- `page` (integer): 当前页码
- `page_size` (integer): 每页数量
- `total_pages` (integer): 总页数（向上取整）
- `items` (array): 当前页的任务历史列表，按时间戳降序排序，每个任务包含：
  - `task_id` (string): 任务ID
  - `conversation_id` (string): 会话ID
  - `task_type` (string): 任务类型（如 "几何建模"、"设计优化" 等）
  - `last_message` (string): 最后一条消息内容（会自动解析 JSON 格式中的 answer 字段）
  - `last_timestamp` (float): 最后一条消息的时间戳
  - `last_time` (string): 格式化的时间字符串（格式：YYYY-MM-DD HH:MM:SS）

### 请求示例

```bash
# 获取所有数据（不传分页参数，兼容旧逻辑）
curl -X GET "http://localhost:8081/api/chat/history" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 获取第一页，每页 20 条（分页模式）
curl -X GET "http://localhost:8081/api/chat/history?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 获取第二页，每页 10 条
curl -X GET "http://localhost:8081/api/chat/history?page=2&page_size=10" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 错误响应

- **500 Internal Server Error**: 获取用户历史失败
  ```json
  {
    "detail": "获取用户历史失败: {错误详情}"
  }
  ```

### 注意事项

1. **排序规则**：返回的任务历史按 `last_timestamp` 降序排序（最新的在前）
2. **消息解析**：系统会自动尝试解析 `last_message` 字段：
   - 如果是 SSE 格式（`event: message_end\ndata: {...}`），会提取 JSON 中的 `answer` 字段
   - 如果是普通 JSON 格式且包含 `answer` 字段，也会提取 `answer` 字段
   - 如果解析失败，则返回原始消息内容
3. **Redis 依赖**：此接口依赖 Redis 存储，需要确保 `settings.REDIS_AVAILABLE` 为 `True` 且 Redis 连接正常

## DELETE /message/{task_id}

### 基本信息
- **方法**：DELETE
- **路由**：`/message/{task_id}`
- **描述**：删除当前用户指定任务的对话历史（删除 Redis 列表与 user_tasks 哈希条目）
- **鉴权**：需要登录（通过 `check_maintenance_mode` 验证）

### 请求参数

**请求头**：
| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| Authorization | string | header | 是 | Bearer token，格式：`Bearer {access_token}` |

**路径参数**：
| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| task_id | string | path | 是 | 任务ID |

### 响应格式

```json
{
  "message": "任务历史已清除",
  "task_id": "task_123",
  "user_id": "user_456"
}
```

### 请求示例

```bash
curl -X DELETE "http://localhost:8081/api/chat/message/task_123" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 错误响应

- **500 Internal Server Error**: 删除会话失败
  ```json
  {
    "detail": "删除会话失败"
  }
  ```

## DELETE /history/{task_id}

### 基本信息
- **方法**：DELETE
- **路由**：`/history/{task_id}`
- **描述**：清除指定任务的对话历史，但保留任务记录（更新 user_tasks 中的 last_message 与 last_timestamp）
- **鉴权**：需要登录（通过 `check_maintenance_mode` 验证）

### 请求参数

**请求头**：
| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| Authorization | string | header | 是 | Bearer token，格式：`Bearer {access_token}` |

**路径参数**：
| 参数名 | 类型 | 位置 | 必填 | 说明 |
|--------|------|------|------|------|
| task_id | string | path | 是 | 任务ID |

### 响应格式

```json
{
  "message": "对话历史已清除",
  "task_id": "task_123",
  "user_id": "user_456"
}
```

### 请求示例

```bash
curl -X DELETE "http://localhost:8081/api/chat/history/task_123" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 错误响应

- **404 Not Found**: 任务未找到
  ```json
  {
    "detail": "任务未找到"
  }
  ```

- **500 Internal Server Error**: 清除对话历史失败
  ```json
  {
    "detail": "清除对话历史失败"
  }
  ```

### 注意事项

- 此接口会删除对话历史消息，但会保留任务记录
- 任务记录中的 `last_message` 会被更新为 "对话历史已清除"
- 任务记录中的 `last_timestamp` 会被更新为当前时间戳

---

## 分页说明

### 通用分页规则

以下两个接口（`/task` 和 `/history`）均支持分页功能：

1. **页码规则**：
   - 页码从 **1** 开始（不是 0）
   - 最小页码为 1
   - 如果请求的页码超过总页数，返回空列表

2. **分页参数说明**：
   - `page` 和 `page_size` 都是**可选参数**
   - **如果不传这两个参数**（或只传其中一个），接口会返回**所有数据**（兼容旧逻辑）
   - **如果两个参数都提供**，才会进行分页处理
   - `page` 最小值为 1
   - `page_size` 范围：1-100
   - 建议根据实际需求设置合理的 `page_size`，避免单次请求数据过大

3. **总页数计算**：
   - `total_pages = ceil(total / page_size)`
   - 如果总记录数为 0，则 `total_pages` 为 0

4. **性能考虑**：
   - 分页是在内存中进行的（先获取所有数据，然后切片）
   - 对于大量数据，建议使用较小的 `page_size` 值
   - 未来可能会优化为在 Redis 层面进行分页

### 分页响应格式

所有分页接口都使用统一的 `PaginatedResponse` 格式：

```json
{
  "total": 100,        // 总记录数
  "page": 1,           // 当前页码
  "page_size": 20,     // 每页数量
  "total_pages": 5,    // 总页数
  "items": [...]       // 当前页的数据列表
}
```

### 使用建议

1. **兼容旧逻辑**：如果不传 `page` 和 `page_size` 参数，接口会返回所有数据，保持与旧版本的兼容性
2. **分页模式**：同时提供 `page` 和 `page_size` 参数时，接口会进行分页处理
3. **首次加载**：使用分页参数（`page=1`, `page_size=20`）获取第一页数据
4. **翻页加载**：根据 `total_pages` 判断是否还有更多数据，逐步增加 `page` 值
5. **调整每页数量**：根据前端展示需求，可以调整 `page_size`（建议不超过 50）

---

## 备注

- **Redis 依赖**：所有对话历史相关接口都依赖 Redis 存储，需要确保：
  - `settings.REDIS_AVAILABLE` 为 `True`
  - Redis 连接正常且在 `app.state.redis` 中注册
  - 如果 Redis 不可用，接口会返回 `NotImplementedError`

- **数据来源**：
  - `/task` 接口从 Redis 的 `message:{user_id}:{task_id}` 键中读取消息列表
  - `/history` 接口从 Redis 的 `user_tasks:{user_id}` 哈希中读取任务列表

- **数据更新**：消息历史通过 `save_or_update_message_in_redis` 函数实时更新到 Redis