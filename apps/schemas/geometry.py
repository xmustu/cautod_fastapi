from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from typing import Optional, Dict, List, AsyncGenerator, Union, List, Literal,Any
from .common import FileItem
class GeometryRequest(BaseModel):
    """几何建模请求模型"""
    # 示例字段
    model_id: str
    parameters: dict

class GeometryResponse(BaseModel):
    """几何建模响应模型"""
    model_id: str
    status: str
    result_url: str



# dify chat-message api 请求信息格式
class MessageRequest(BaseModel):
    inputs: object
    query: str
    response_mode: Optional[str] = "streaming"  # 目前仅支持 streaming
    conversation_id: Optional[str] = None
    user: Optional[str] = "abc-123"  # 用户标识符
    files: Optional[List[FileItem]] = None
    auto_generate_name: Optional[bool] = False


"""dify chat-message api  响应模型 开始"""

# ------------------ 各事件体 ------------------
class MessageChunk(BaseModel):
    event: Literal["message"]
    task_id: str
    message_id: str
    conversation_id: str
    answer: str
    created_at: int

class MessageFileChunk(BaseModel):
    event: Literal["message_file"]
    id: str
    type: Literal["image"]
    belongs_to: Literal["assistant"]
    url: str
    conversation_id: str

class MessageEndChunk(BaseModel):
    event: Literal["message_end"]
    task_id: str
    message_id: str
    conversation_id: str
    metadata: dict

# class TTSMessageChunk(BaseModel):
#     event: Literal["tts_message"]
#     task_id: str
#     message_id: str
#     audio: str  # base64 mp3
#     created_at: int

# class TTSMessageEndChunk(BaseModel):
#     event: Literal["tts_message_end"]
#     task_id: str
#     message_id: str
#     audio: str = ""  # empty
#     created_at: int

class MessageReplaceChunk(BaseModel):
    event: Literal["message_replace"]
    task_id: str
    message_id: str
    conversation_id: str
    answer: str
    created_at: int

class WorkflowStartedChunk(BaseModel):
    event: Literal["workflow_started"]
    task_id: str
    workflow_run_id: str
    data: dict

class NodeStartedChunk(BaseModel):
    event: Literal["node_started"]
    task_id: str
    workflow_run_id: str
    data: dict

class NodeFinishedChunk(BaseModel):
    event: Literal["node_finished"]
    task_id: str
    workflow_run_id: str
    data: dict

class WorkflowFinishedChunk(BaseModel):
    event: Literal["workflow_finished"]
    task_id: str
    workflow_run_id: str
    data: dict

class ErrorChunk(BaseModel):
    event: Literal["error"]
    task_id: str
    message_id: str
    status: int
    code: str
    message: str

class PingChunk(BaseModel):
    event: Literal["ping"]

# ------------------ 联合模型 ------------------
StreamChunk = Union[
    MessageChunk,
    MessageFileChunk,
    MessageEndChunk,
    # TTSMessageChunk,
    # TTSMessageEndChunk,
    MessageReplaceChunk,
    WorkflowStartedChunk,
    NodeStartedChunk,
    NodeFinishedChunk,
    WorkflowFinishedChunk,
    ErrorChunk,
    PingChunk,
]

class ChunkChatCompletionResponse(BaseModel):
    """SSE 流式块"""
    chunk: StreamChunk



# ---下一轮建议问题的模型-----
class SuggestedQuestionsResponse(BaseModel):
    result: str
    data: List[str]


"""dify chat-message api  响应模型 结束"""  

