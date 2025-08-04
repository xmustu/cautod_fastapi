# 后端 API 接口说明 (V1)

本文档定义了 CAutoD 前端应用所需的后端 API 接口。所有接口都应部署在 `http://127.0.0.1:8080`。

## 认证

所有需要认证的接口，前端都会在请求头中附加 `Authorization` 字段：

```
Authorization: Bearer <your_jwt_token>
```

---

## 1. 任务管理

### 1.1 创建新任务

这是所有工作流程（几何建模、零件检索等）的第一步。前端会先调用此接口来注册一个新任务，并获取由后端生成的 `task_id`。

-   **Endpoint**: `POST /tasks`
-   **用途**: 创建一个新的任务实例。
-   **请求体 (Request Body)**:
    ```json
    {
      "conversation_id": "string", // 必需，任务所属的对话ID
      "task_type": "string",       // 必需，任务类型，枚举值见下文
      "details": "object"          // 可选，与任务相关的附加信息，如初始查询文本
    }
    ```
-   **`task_type` 枚举值**:
    -   `geometry`
    -   `part_retrieval`
    -   `design_optimization`
-   **响应体 (Response Body)**:
    成功时，返回新创建的完整任务对象。
    ```json
    {
      "task_id": "string",           // 由后端生成的唯一任务ID
      "conversation_id": "string",
      "task_type": "string",
      "status": "pending",         // 任务初始状态
      "created_at": "datetime",      // 创建时间
      "details": "object"
    }
    ```

### 1.2 执行任务

这是所有工作流程的核心执行接口。前端在获取到 `task_id` 后，会调用此接口来实际执行任务。后端需要根据 `task_type` 来路由到不同的内部服务。

-   **Endpoint**: `POST /tasks/execute`
-   **用途**: 执行一个已创建的任务。
-   **请求体 (Request Body)**:
    一个包含所有执行所需参数的JSON对象。
    ```json
    {
      "task_id": "string",           // 必需，要执行的任务ID
      "conversation_id": "string",   // 必需
      "task_type": "string",         // 必需，用于后端路由
      "query": "string",             // 可选，用户的文本输入
      "file_url": "string",          // 可选，上传文件的URL
      // ... 其他特定于任务的参数，例如设计优化的约束条件
    }
    ```
-   **响应体 (Response Body)**:
    响应格式取决于任务类型。
    -   **对于 `geometry` (流式响应)**:
        -   **Content-Type**: `text/event-stream`
        -   后端需要以 Server-Sent Events (SSE) 的形式持续推送JSON对象。每个对象包含 `event` 和 `data` 字段。
        -   **示例**:
            ```
            event: text_chunk
            data: {"text": "正在分析您的需求..."}

            event: message_end
            data: {"answer": "模型已生成。", "metadata": {"preview_image": "url/to/image.png"}}
            ```
    -   **对于 `part_retrieval` 和 `design_optimization` (一次性响应)**:
        -   **Content-Type**: `application/json`
        -   返回一个包含任务结果的JSON对象。
        -   **示例 (`part_retrieval`)**:
            ```json
            {
              "data": {
                "parts": [
                  { "id": "part-01", "name": "零件A", "imageUrl": "url/to/image.png" }
                ]
              }
            }
            ```
        -   **示例 (`design_optimization`)**:
            ```json
            {
              "optimized_file": "path/to/optimized.stl",
              "best_params": [1.0, 2.5, 3.0],
              "final_volume": 123.45,
              "final_stress": 56.78,
              "unit": { "volume": "cm^3", "stress": "MPa" },
              "constraint_satisfied": true
            }
            ```

---

## 2. 历史记录

### 2.1 获取对话下的所有任务

用于在历史记录页面展示一个对话下的所有任务列表。

-   **Endpoint**: `GET /conversations/:conversationId/tasks`
-   **用途**: 获取指定对话的所有任务。
-   **URL 参数**:
    -   `conversationId`: 对话的唯一ID。
-   **响应体 (Response Body)**:
    一个包含任务对象的数组。
    ```json
    [
      {
        "task_id": "string",
        "task_type": "string", // 注意：前端显示时会映射为中文名
        "summary": "string",   // 任务的简要描述
        "created_at": "datetime",
        "status": "string"     // 例如 "完成", "进行中", "失败"
      }
    ]
    ```

---
**注意**: `GET /conversation_all` 接口（用于获取所有对话列表）应继续保持不变，前端依赖此接口来渲染侧边栏和历史页面的顶层列表。



## 3.对话管理
## 概述

本文档详细描述了基于FastAPI实现的对话管理接口，遵循RESTful规范。这些接口用于管理用户与AI之间的对话历史，支持流式对话生成、获取历史记录以及删除操作等功能。

## 基础信息

- **基础路径**：接口的基础路径由路由配置决定
- **认证方式**：通过`get_current_active_user`依赖项进行用户认证（
- **数据存储**：使用Redis存储对话消息和用户任务信息
- **响应格式**：除流式响应外，均返回JSON格式数据

## 接口详情

### 1. 对话管理首页

- **路径**：`GET /chat`
- **标签**：对话管理
- **描述**：对话管理模块的首页接口
- **请求参数**：无
- **响应示例**：
  ```json
  {
    "message": "对话管理首页"
  }
  ```
- **状态码**：200（成功）

### 2. 流式对话生成

- **路径**：`POST /chat/stream`
- **标签**：对话管理
- **摘要**：流式对话生成
- **描述**：接收用户消息并以流式方式返回AI的响应
- **请求体**：包含用户ID、任务ID和用户消息的请求对象
- **响应类型**：text/event-stream（SSE流式响应）
- **响应头**：
  - Cache-Control: no-cache
  - Connection: keep-alive
  - Access-Control-Allow-Origin: *
- **响应示例**（流式输出）：
  ```json
  {"role": "assistant", "content": "您好，", "timestamp": "2023-07-31T10:00:00"}
  {"role": "assistant", "content": "有什么可以帮助您的吗？", "timestamp": "2023-07-31T10:00:01"}
  ```
- **状态码**：200（成功）

### 3. 获取任务的对话历史

- **路径**：`GET /chat/task`
- **标签**：对话管理
- **摘要**：获取任务的对话历史
- **描述**：根据用户ID和任务ID获取该任务下的所有对话历史记录
- **请求参数**：
  - `task_id`（必填）：任务ID，字符串类型
- **响应示例**：
  ```json
  {
    "task_id": "task123",
    "message": [
      {
        "role": "user",
        "content": "你好",
        "timestamp": "2023-07-31T09:00:00"
      },
      {
        "role": "assistant",
        "content": "您好，有什么可以帮助您的吗？",
        "timestamp": "2023-07-31T09:00:01"
      }
    ],
    "total": 2
  }
  ```
- **状态码**：
  - 200：成功
  - 500：获取聊天历史失败

### 4. 获取用户对话历史记录

- **路径**：`GET /chat/history`
- **标签**：对话管理
- **摘要**：获取用户对话历史记录
- **描述**：根据用户ID获取该用户的所有任务列表及最后一条消息信息
- **请求参数**：
  - 无
- **响应示例**：
  ```json
  {
    "user_id": "user123",
    "history": [
      {
        "task_id": "task123",
        "last_message": "您好，有什么可以帮助您的吗？",
        "last_timestamp": "1627731601",
        "last_time": "2023-07-31 09:00:01"
      }
    ],
    "total": 1
  }
  ```
- **状态码**：
  - 200：成功
  - 500：获取用户历史失败

### 5. 删除任务的对话历史

- **路径**：`DELETE /chat/message/{task_id}`
- **标签**：对话管理
- **摘要**：删除任务的对话历史
- **描述**：根据用户ID和任务ID完全删除该任务及其所有对话历史
- **路径参数**：
  - `task_id`：任务ID，字符串类型
- **请求参数**：
    - 无
- **响应示例**：
  ```json
  {
    "message": "任务历史已清除",
    "task_id": "task123",
    "user_id": "user123"
  }
  ```
- **状态码**：
  - 200：成功
  - 500：删除会话失败

### 6. 清除指定任务的对话历史，但保留任务记录

- **路径**：`DELETE /chat/history/{task_id}`
- **标签**：对话管理
- **摘要**：清除指定任务的对话历史，但保留任务记录
- **描述**：根据用户ID和任务ID清除该任务的对话历史，但保留任务本身的记录
- **路径参数**：
  - `task_id`：任务ID，字符串类型
- **请求参数**：
  - 无
- **响应示例**：无响应体
- **状态码**：
  - 200：成功
  - 500：清除对话历史失败

## 数据模型

### Message（消息模型）

```
{
  "role": string,      // 发送者角色："user"(用户) 或 "assistant"(AI)
  "content": string,   // 消息内容
  "timestamp": datetime // 消息时间戳，默认当前时间
}
```

### SSETextChunk（流式响应消息块）

```
{
  "role": string,      // 发送者角色："user"(用户)、"assistant"(AI) 或 "error"(错误)
  "content": string,   // 消息内容
  "timestamp": datetime // 消息时间戳
}
```

## 错误处理

所有接口在发生错误时，都会返回HTTP 500状态码，并在响应体中包含错误详情：

```json
{
  "detail": "错误描述信息"
}
```

## 注意事项

1. 所有接口依赖Redis服务，如果Redis不可用，会返回500错误
2. 流式响应接口(`/stream`)使用SSE（Server-Sent Events）协议，客户端需要支持该协议才能正确处理响应
3. 时间戳格式遵循ISO 8601标准
4. 接口设计中包含用户认证依赖项，但部分接口暂未应用，实际使用中可根据需要添加`current_user: User = Depends(get_current_active_user)`参数进行认证控制
