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
