"""
schemas/__init__.py

该文件是 `schemas` 模块的初始化文件，主要用于统一导入和管理所有的 Pydantic 模型。

### 文件作用
1. **模块化管理**：
   - 将各业务模块（如用户、任务、对话、几何建模、优化等）的 Pydantic 模型集中管理。
   - 通过分模块导入，保持代码结构清晰，便于维护和扩展。

2. **统一导出**：
   - 使用 `__all__` 列表定义模块的公开接口，明确哪些模型可以被外部导入。
   - 外部模块可以通过 `from apps.schemas import ...` 的方式直接使用所需的模型。

### 使用方法
1. **导入模型**：
   - 在其他模块中，只需从 `schemas` 导入所需的模型。例如：
     ```python
     from apps.schemas import TaskCreateRequest, OptimizeRequest
     ```

2. **新增模型**：
   - 如果需要新增模型，请在对应的schema文件（如 [tasks.py]、[geometry.py]）中定义模型，并在此文件中导入。
   - 同时，将新增的模型添加到 [__all__] 列表中，确保可以被外部访问。

3. **分模块管理**：
   - 每个文件对应一个业务模块（如 [tasks.py]对应任务相关模型），便于开发者快速定位和修改。

### 文件结构
- [common.py]：通用模型（如文件信息）。
- [user.py]：用户相关模型（如认证配置）。
- [tasks.py]：任务相关模型（如任务创建、执行、SSE 传输）。
- [conversations.py]：对话相关模型（如对话创建、响应）。
- [geometry.py]：几何建模相关模型。
- [optimize.py]：优化相关模型。
- [chat.py]：聊天相关模型。

通过这种模块化管理方式，`schemas` 模块能够高效地支持整个项目的 Pydantic 模型需求。
"""


from .common import (
    FileItem,
    FileRequest
)

from .user import (
    AuthConfig
)


from .chat import (
    Message
)

from .conversations import (
    ConversationCreateRequest,
    ConversationResponse,
    ConversationOut
)

from .tasks import (
    TaskOut,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskExecuteRequest,
    PendingTaskResponse,
    GenerationMetadata,
    SSEConversationInfo,
    SSETextChunk,
    SSEResponse,
    PartData,
    SSEPartChunk,
    SSEImageChunk
)


from .chat import (
    Message
)

from .geometry import (
    GeometryRequest,
    GeometryResponse,
    MessageRequest,
    MessageChunk,
    MessageFileChunk,
    MessageEndChunk,
    MessageReplaceChunk,
    WorkflowStartedChunk,
    NodeStartedChunk,
    NodeFinishedChunk,
    WorkflowFinishedChunk,
    ErrorChunk,
    PingChunk,
    StreamChunk,
    ChunkChatCompletionResponse,
    SuggestedQuestionsResponse
)

from .optimize import (
    OptimizeRequest,
    UnitInfo,
    OptimizeResult,
    OptimizationParamsRequest,
    AlgorithmRequest,
    TaskStatus,
    HealthStatus
)

__all__ = [
    # user.py
    "AuthConfig"
    
    # common.py
    "FileItem",
    "FileRequest",

    # conversations.py
    "ConversationCreateRequest",
    "ConversationResponse",
    "ConversationOut",

    # tasks.py
    "TaskOut",
    "TaskCreateRequest",
    "TaskCreateResponse",
    "TaskExecuteRequest",
    "PendingTaskResponse",
    "GenerationMetadata",
    "SSEConversationInfo",
    "SSETextChunk",
    "SSEResponse",
    "PartData",
    "SSEPartChunk",
    "SSEImageChunk",

    # chat.py
    "Message",

    # geometry.py
    "GeometryRequest",
    "GeometryResponse",
    "MessageRequest",
    "MessageChunk",
    "MessageFileChunk",
    "MessageEndChunk",
    "MessageReplaceChunk",
    "WorkflowStartedChunk",
    "NodeStartedChunk",
    "NodeFinishedChunk",
    "WorkflowFinishedChunk",
    "ErrorChunk",
    "PingChunk",
    "StreamChunk",
    "ChunkChatCompletionResponse",
    "SuggestedQuestionsResponse",

    # optimize.py
    "OptimizeRequest",
    "UnitInfo",
    "OptimizeResult",
    "OptimizationParamsRequest",
    "AlgorithmRequest",
    "TaskStatus",
    "HealthStatus"
]