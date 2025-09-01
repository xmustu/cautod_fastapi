from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from typing import Optional, Dict, List, AsyncGenerator, Union, List, Literal,Any
from datetime import datetime
from .tasks import TaskOut
from .geometry import SuggestedQuestionsResponse


# 定义请求和响应模型

# 创建会话
class ConversationCreateRequest(BaseModel):
    title: str = Field(..., max_length=100, description="新会话的标题")

class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: int
    title: str
    created_at: datetime

    class Config:
        from_attributes = True # Pydantic V2, or orm_mode = True for V1

class ConversationOut(BaseModel):
    """对话输出模型"""
    conversation_id: str
    user_id: int
    title: str
    created_at: datetime
    tasks: List[TaskOut] = []

    class Config:
        from_attributes = True




